from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.api.serializers import CATEGORY_LATERAL, REPO_CARD_SQL, repo_card
from app.core.cache import with_cache
from app.core.db import get_pool

router = APIRouter(tags=["meta"])

PERIOD_ORDER = {
    "day": "r.hot_score DESC",
    "week": "r.star_growth_7d DESC, r.hot_score DESC",
    "month": "r.star_growth_30d DESC, r.hot_score DESC",
}


@router.get("/trending")
async def trending(period: str = "day", category: str | None = None, limit: int = Query(20, ge=1, le=100)):
    order = PERIOD_ORDER.get(period, PERIOD_ORDER["day"])

    async def produce():
        pool = await get_pool()
        where, params = ["NOT r.is_archived"], []
        if category:
            params.append(category)
            where.append(
                "EXISTS (SELECT 1 FROM repo_categories rc JOIN categories c ON c.id = rc.category_id "
                "WHERE rc.repo_id = r.id AND c.slug = $1)"
            )
        sql = f"""SELECT {REPO_CARD_SQL} FROM repositories r {CATEGORY_LATERAL}
                  WHERE {" AND ".join(where)} ORDER BY {order} LIMIT {limit}"""
        rows = await pool.fetch(sql, *params)
        return {"data": [repo_card(x) for x in rows], "meta": {"period": period}}

    return await with_cache(f"trending:{period}:{category}:{limit}", produce)


@router.get("/categories")
async def categories():
    async def produce():
        pool = await get_pool()
        rows = await pool.fetch(
            """SELECT c.slug, c.name, c.display_order, count(rc.repo_id) AS repo_count
               FROM categories c LEFT JOIN repo_categories rc ON rc.category_id = c.id
               GROUP BY c.id ORDER BY c.display_order"""
        )
        return {"data": [dict(x) for x in rows]}

    return await with_cache("categories", produce)


@router.get("/stats/dashboard")
async def dashboard_stats():
    async def produce():
        pool = await get_pool()
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT count(*) FROM repositories WHERE NOT is_archived")
            new_today = await conn.fetchval(
                "SELECT count(*) FROM repositories WHERE first_seen_at::date = CURRENT_DATE"
            )
            new_yesterday = await conn.fetchval(
                "SELECT count(*) FROM repositories WHERE first_seen_at::date = CURRENT_DATE - 1"
            )
            top_week = await conn.fetchrow(
                "SELECT full_name, star_growth_7d FROM repositories WHERE NOT is_archived ORDER BY star_growth_7d DESC LIMIT 1"
            )
            top_month = await conn.fetchrow(
                "SELECT full_name, star_growth_30d FROM repositories WHERE NOT is_archived ORDER BY star_growth_30d DESC LIMIT 1"
            )
            top_categories = await conn.fetch(
                """SELECT c.slug, c.name, count(*) AS repo_count
                   FROM repo_categories rc JOIN categories c ON c.id = rc.category_id
                   GROUP BY c.slug, c.name ORDER BY repo_count DESC LIMIT 8"""
            )
            last_run = await conn.fetchrow(
                "SELECT started_at, finished_at, status FROM crawl_runs ORDER BY id DESC LIMIT 1"
            )
        return {
            "total_repos": total,
            "new_today": new_today,
            "new_yesterday": new_yesterday,
            "top_weekly": dict(top_week) if top_week else None,
            "top_monthly": dict(top_month) if top_month else None,
            "top_categories": [dict(x) for x in top_categories],
            "last_run": dict(last_run) if last_run else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return await with_cache("stats:dashboard", produce)


@router.get("/updates/daily")
async def daily_updates(limit: int = Query(20, ge=1, le=100)):
    async def produce():
        pool = await get_pool()
        async with pool.acquire() as conn:
            new_repos = await conn.fetch(
                f"""SELECT {REPO_CARD_SQL} FROM repositories r {CATEGORY_LATERAL}
                    WHERE r.first_seen_at::date = CURRENT_DATE
                    ORDER BY r.stars DESC LIMIT {limit}"""
            )
            movers = await conn.fetch(
                f"""SELECT {REPO_CARD_SQL} FROM repositories r {CATEGORY_LATERAL}
                    WHERE NOT r.is_archived AND r.star_growth_7d > 0
                    ORDER BY r.star_growth_7d DESC LIMIT {limit}"""
            )
            new_summaries = await conn.fetch(
                """SELECT r.full_name, s.created_at FROM ai_summaries s
                   JOIN repositories r ON r.id = s.repo_id
                   WHERE s.created_at::date = CURRENT_DATE ORDER BY s.created_at DESC LIMIT 50"""
            )
        return {
            "new_repos": [repo_card(x) for x in new_repos],
            "top_movers": [repo_card(x) for x in movers],
            "new_summaries": [dict(x) for x in new_summaries],
        }

    return await with_cache(f"updates:daily:{limit}", produce)
