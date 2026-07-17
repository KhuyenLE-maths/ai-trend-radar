"""Hacker News (Algolia API) — tín hiệu community mention cho repo GitHub."""
import logging
import re
import time
from datetime import datetime, timezone

import httpx

log = logging.getLogger("pipeline.hn")

ALGOLIA = "https://hn.algolia.com/api/v1/search"
GH_RE = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)")


async def fetch_mentions(min_points: int = 50, days: int = 3) -> list[dict]:
    """Story chứa link GitHub, điểm cao, trong N ngày gần nhất."""
    since = int(time.time()) - days * 86400
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                ALGOLIA,
                params={
                    "query": "github.com",
                    "tags": "story",
                    "numericFilters": f"points>{min_points},created_at_i>{since}",
                    "hitsPerPage": 100,
                },
            )
            r.raise_for_status()
            for hit in r.json().get("hits", []):
                m = GH_RE.search(hit.get("url") or "") or GH_RE.search(hit.get("story_text") or "")
                if not m:
                    continue
                full_name = m.group(1).removesuffix(".git")
                out.append({
                    "full_name": full_name,
                    "external_id": hit["objectID"],
                    "title": hit.get("title"),
                    "url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    "score": hit.get("points", 0),
                    "mentioned_at": datetime.fromtimestamp(hit.get("created_at_i", 0), tz=timezone.utc),
                })
    except Exception as e:
        log.warning("HN fetch fail: %s", e)
    log.info("hn: %s mentions", len(out))
    return out


async def save_mentions(pool, mentions: list[dict]) -> int:
    """Chỉ lưu mention của repo đã có trong DB (map theo full_name)."""
    saved = 0
    async with pool.acquire() as conn:
        for m in mentions:
            repo_id = await conn.fetchval(
                "SELECT id FROM repositories WHERE lower(full_name) = lower($1)", m["full_name"]
            )
            if not repo_id:
                continue
            await conn.execute(
                """INSERT INTO repo_mentions (repo_id, source, external_id, title, url, score, mentioned_at)
                   VALUES ($1,'hackernews',$2,$3,$4,$5,$6)
                   ON CONFLICT (source, external_id) DO UPDATE SET score = EXCLUDED.score""",
                repo_id, m["external_id"], m["title"], m["url"], m["score"], m["mentioned_at"],
            )
            saved += 1
    return saved
