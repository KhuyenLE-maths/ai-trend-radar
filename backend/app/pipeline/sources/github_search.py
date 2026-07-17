"""Discover: tìm repo AI mới qua GitHub Search API theo bộ topic."""
import logging
from datetime import date, datetime, timedelta

import asyncpg

from app.core.config import settings
from app.pipeline.sources.github_client import rest_get
from app.pipeline.steps.filter_ai import relevance_score

log = logging.getLogger("pipeline.discover")

# Bộ topic phủ các domain trong tài liệu thiết kế (mục 3.2)
TOPICS = [
    "llm", "ai-agents", "agents", "agentic-ai", "multi-agent", "rag",
    "mcp", "model-context-protocol", "machine-learning", "deep-learning",
    "mlops", "llmops", "computer-vision", "nlp", "speech-recognition",
    "text-to-speech", "vector-database", "fine-tuning", "inference",
    "generative-ai", "ai-coding", "llm-evaluation", "synthetic-data", "cuda",
]

UPSERT_SQL = """
INSERT INTO repositories (
  github_id, full_name, owner, name, url, homepage, description, logo_url,
  language, license_spdx, topics, is_archived, is_fork,
  stars, forks, watchers, open_issues, repo_created_at, repo_pushed_at, ai_relevance
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
ON CONFLICT (github_id) DO UPDATE SET
  full_name = EXCLUDED.full_name, description = EXCLUDED.description,
  topics = EXCLUDED.topics, ai_relevance = GREATEST(coalesce(repositories.ai_relevance,0), EXCLUDED.ai_relevance)
"""


def _parse_iso_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _item_to_row(it: dict, score: float) -> tuple:
    lic = (it.get("license") or {}).get("spdx_id")
    return (
        it["id"], it["full_name"], it["owner"]["login"], it["name"],
        it["html_url"], it.get("homepage"), (it.get("description") or "")[:512] or None,
        it["owner"].get("avatar_url"), it.get("language"),
        None if lic in (None, "NOASSERTION") else lic,
        [t.lower() for t in (it.get("topics") or [])][:20],
        it.get("archived", False), it.get("fork", False),
        it.get("stargazers_count", 0), it.get("forks_count", 0),
        it.get("watchers_count", 0), it.get("open_issues_count", 0),
        _parse_iso_datetime(it.get("created_at")), _parse_iso_datetime(it.get("pushed_at")), score,
    )


async def discover(pool: asyncpg.Pool) -> dict:
    """Chạy các truy vấn search theo topic; upsert repo vượt ngưỡng AI-relevance."""
    since_pushed = (date.today() - timedelta(days=30)).isoformat()
    since_created = (date.today() - timedelta(days=21)).isoformat()
    queries = []
    for t in TOPICS:
        # Repo có lực (active + đủ sao)
        queries.append(f"topic:{t} pushed:>{since_pushed} stars:>{settings.discover_min_stars}")
        # Repo mới toanh (bắt sớm xu hướng)
        queries.append(f"topic:{t} created:>{since_created} stars:>10")

    seen: set[int] = set()
    inserted = scanned = 0
    async with pool.acquire() as conn:
        for q in queries:
            for page in range(1, settings.discover_pages_per_query + 1):
                try:
                    data = await rest_get(
                        "/search/repositories",
                        {"q": q, "sort": "stars", "order": "desc", "per_page": 100, "page": page},
                    )
                except Exception as e:  # 1 truy vấn fail không được chặn các truy vấn khác
                    log.warning("search fail q=%r page=%s: %s", q, page, e)
                    break
                items = data.get("items", [])
                scanned += len(items)
                for it in items:
                    if it["id"] in seen or it.get("fork") or it.get("archived"):
                        continue
                    seen.add(it["id"])
                    score = relevance_score(
                        it.get("name", ""), it.get("description") or "", it.get("topics") or []
                    )
                    if score < settings.ai_filter_threshold:
                        continue
                    await conn.execute(UPSERT_SQL, *_item_to_row(it, score))
                    inserted += 1
                if len(items) < 100:
                    break
    log.info("discover: scanned=%s accepted=%s", scanned, inserted)
    return {"scanned": scanned, "accepted": inserted}
