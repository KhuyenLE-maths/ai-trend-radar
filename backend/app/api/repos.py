import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.api.serializers import CATEGORY_LATERAL, REPO_CARD_SQL, repo_card
from app.core.cache import with_cache
from app.core.db import get_pool

router = APIRouter(tags=["repos"])

SORT_MAP = {
    "hot": "r.hot_score DESC, r.stars DESC",
    "new": "r.first_seen_at DESC",
    "stars": "r.stars DESC",
    "growth_7d": "r.star_growth_7d DESC",
    "growth_30d": "r.star_growth_30d DESC",
}


def _list_filters(category, language, license_, min_stars, min_growth_7d, updated_within):
    """Trả về (mảnh WHERE, params) — dùng chung cho /repos và /trending."""
    where, params = ["NOT r.is_archived"], []

    def p(v):
        params.append(v)
        return f"${len(params)}"

    if category:
        where.append(
            f"EXISTS (SELECT 1 FROM repo_categories rc JOIN categories c ON c.id = rc.category_id "
            f"WHERE rc.repo_id = r.id AND c.slug = {p(category)})"
        )
    if language:
        where.append(f"r.language ILIKE {p(language)}")
    if license_:
        where.append(f"r.license_spdx ILIKE {p(license_ + '%')}")
    if min_stars:
        where.append(f"r.stars >= {p(min_stars)}")
    if min_growth_7d:
        where.append(f"r.star_growth_7d >= {p(min_growth_7d)}")
    if updated_within:
        where.append(f"coalesce(r.last_commit_at, r.repo_pushed_at) > now() - ({p(updated_within)} || ' days')::interval")
    return where, params


@router.get("/repos")
async def list_repos(
    category: str | None = None,
    language: str | None = None,
    license: str | None = None,
    min_stars: int | None = None,
    min_growth_7d: int | None = None,
    updated_within: int | None = Query(None, description="số ngày"),
    sort: str = "hot",
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
):
    order = SORT_MAP.get(sort, SORT_MAP["hot"])
    where, params = _list_filters(category, language, license, min_stars, min_growth_7d, updated_within)
    key = f"repos:{category}:{language}:{license}:{min_stars}:{min_growth_7d}:{updated_within}:{sort}:{page}:{per_page}"

    async def produce():
        pool = await get_pool()
        where_sql = " AND ".join(where)
        offset = (page - 1) * per_page
        sql = f"""
            SELECT {REPO_CARD_SQL} FROM repositories r {CATEGORY_LATERAL}
            WHERE {where_sql} ORDER BY {order}
            LIMIT {per_page} OFFSET {offset}"""
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            total = await conn.fetchval(f"SELECT count(*) FROM repositories r WHERE {where_sql}", *params)
        return {
            "data": [repo_card(x) for x in rows],
            "pagination": {"page": page, "per_page": per_page, "total": total},
            "meta": {"generated_at": datetime.now(timezone.utc).isoformat()},
        }

    return await with_cache(key, produce)


@router.get("/search")
async def search(q: str = Query(..., min_length=1), page: int = Query(1, ge=1), per_page: int = Query(24, ge=1, le=100)):
    """Hỗ trợ operator đơn giản: owner:xxx  tag:yyy  category:zzz + free text."""
    owner = tag = category = None
    terms = []
    for tok in q.split():
        if m := re.match(r"^owner:(.+)$", tok):
            owner = m.group(1)
        elif m := re.match(r"^tag:(.+)$", tok):
            tag = m.group(1).lower()
        elif m := re.match(r"^category:(.+)$", tok):
            category = m.group(1).lower()
        else:
            terms.append(tok)
    text = " ".join(terms)

    async def produce():
        pool = await get_pool()
        where, params = ["NOT r.is_archived"], []

        def p(v):
            params.append(v)
            return f"${len(params)}"

        if owner:
            where.append(f"r.owner ILIKE {p(owner)}")
        if tag:
            where.append(f"{p(tag)} = ANY(r.topics)")
        if category:
            where.append(
                f"EXISTS (SELECT 1 FROM repo_categories rc JOIN categories c ON c.id = rc.category_id "
                f"WHERE rc.repo_id = r.id AND c.slug = {p(category)})"
            )
        rank_expr = "r.hot_score"
        if text:
            t = p(text)
            where.append(
                f"(r.search_vector @@ websearch_to_tsquery('english', {t}) "
                f"OR r.full_name ILIKE '%' || {t} || '%' OR similarity(r.full_name, {t}) > 0.25)"
            )
            rank_expr = (
                f"GREATEST(ts_rank(r.search_vector, websearch_to_tsquery('english', {t})) * 10, "
                f"similarity(r.full_name, {t})) * (1 + r.hot_score / 100.0)"
            )
        offset = (page - 1) * per_page
        sql = f"""
            SELECT {REPO_CARD_SQL} FROM repositories r {CATEGORY_LATERAL}
            WHERE {" AND ".join(where)}
            ORDER BY {rank_expr} DESC LIMIT {per_page} OFFSET {offset}"""
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            total = await conn.fetchval(
                f"SELECT count(*) FROM repositories r WHERE {' AND '.join(where)}", *params
            )
        return {
            "data": [repo_card(x) for x in rows],
            "pagination": {"page": page, "per_page": per_page, "total": total},
            "meta": {"q": q},
        }

    return await with_cache(f"search:{q}:{page}:{per_page}", produce)


@router.get("/repos/{owner}/{name}")
async def repo_detail(owner: str, name: str):
    async def produce():
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT r.id AS _id, {REPO_CARD_SQL} FROM repositories r {CATEGORY_LATERAL}
                    WHERE lower(r.full_name) = lower($1)""",
                f"{owner}/{name}",
            )
            if not row:
                return None
            repo_id = row["_id"]
            d = repo_card(row)
            d.pop("_id", None)

            spark = await conn.fetch(
                "SELECT snapshot_date, stars FROM repo_snapshots WHERE repo_id = $1 ORDER BY snapshot_date DESC LIMIT 30",
                repo_id,
            )
            d["sparkline_30d"] = [x["stars"] for x in reversed(spark)]

            summary = await conn.fetchrow(
                "SELECT content, model, created_at FROM ai_summaries WHERE repo_id = $1 ORDER BY created_at DESC LIMIT 1",
                repo_id,
            )
            if summary:
                content = summary["content"]
                d["ai_summary"] = {
                    "content": json.loads(content) if isinstance(content, str) else content,
                    "model": summary["model"],
                    "created_at": summary["created_at"],
                }
            else:
                d["ai_summary"] = None

            mentions = await conn.fetch(
                "SELECT source, title, url, score, mentioned_at FROM repo_mentions WHERE repo_id = $1 ORDER BY mentioned_at DESC LIMIT 10",
                repo_id,
            )
            d["mentions"] = [dict(m) for m in mentions]

            similar = await conn.fetch(
                f"""SELECT DISTINCT ON (r.id) {REPO_CARD_SQL}, r.id FROM repositories r {CATEGORY_LATERAL}
                    JOIN repo_categories rc2 ON rc2.repo_id = r.id
                    WHERE rc2.category_id IN (SELECT category_id FROM repo_categories WHERE repo_id = $1)
                      AND r.id <> $1 AND NOT r.is_archived
                    ORDER BY r.id, r.hot_score DESC""",
                repo_id,
            )
            similar_sorted = sorted((repo_card(s) for s in similar), key=lambda x: -(x["hot_score"] or 0))[:6]
            for s in similar_sorted:
                s.pop("id", None)
            d["similar"] = similar_sorted
        return d

    data = await with_cache(f"detail:{owner}/{name}".lower(), produce)
    if data is None:
        raise HTTPException(404, "Repository not found")
    return data


@router.get("/repos/{owner}/{name}/snapshots")
async def repo_snapshots(owner: str, name: str, days: int = Query(90, ge=1, le=730)):
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT s.snapshot_date, s.stars, s.forks, s.watchers, s.open_issues, s.contributors
           FROM repo_snapshots s JOIN repositories r ON r.id = s.repo_id
           WHERE lower(r.full_name) = lower($1) AND s.snapshot_date > CURRENT_DATE - $2::int
           ORDER BY s.snapshot_date""",
        f"{owner}/{name}",
        days,
    )
    return {"data": [dict(x) for x in rows]}
