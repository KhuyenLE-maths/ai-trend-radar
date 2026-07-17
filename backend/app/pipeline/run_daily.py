"""Orchestrator pipeline hàng ngày (mục 8.2).

Thứ tự: discover → track → trending flags → mentions → categorize → rank
        → summarize → invalidate cache → notify.
Mỗi bước fail-soft: lỗi được ghi vào crawl_runs.stats, các bước sau vẫn chạy
nếu không phụ thuộc cứng. Redis lock chống chạy chồng.
"""
import json
import logging
import traceback

import httpx

from app.core.cache import acquire_pipeline_lock, invalidate_all, release_pipeline_lock
from app.core.config import settings
from app.core.db import get_pool, init_db
from app.pipeline.sources import github_graphql, github_search, github_trending, hackernews
from app.pipeline.steps import categorize, rank, summarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")


async def _notify_slack(text: str) -> None:
    if not settings.slack_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.slack_webhook_url, json={"text": text})
    except Exception as e:
        log.warning("slack notify fail: %s", e)


async def run_daily(trigger: str = "cron") -> dict:
    if not await acquire_pipeline_lock():
        log.warning("Pipeline đang chạy (lock tồn tại) — bỏ qua lần trigger này.")
        return {"skipped": "locked"}

    await init_db()
    pool = await get_pool()
    run_id = await pool.fetchval(
        "INSERT INTO crawl_runs (status, trigger) VALUES ('running', $1) RETURNING id", trigger
    )
    stats: dict = {}
    errors: list[str] = []

    async def step(name: str, coro):
        try:
            stats[name] = await coro
            await pool.execute(
                "UPDATE crawl_runs SET stats = $1 WHERE id = $2", json.dumps(stats, default=str), run_id
            )
        except Exception as e:
            log.error("step %s failed: %s\n%s", name, e, traceback.format_exc())
            errors.append(f"{name}: {e}")
            stats[name] = {"error": str(e)}

    try:
        # 1. Discover repo mới qua Search API
        await step("discover", github_search.discover(pool))

        # 2. Tín hiệu ngoài: trending + HN (fail-soft, có thể rỗng)
        trending_names: set[str] = set()
        try:
            trending_names = await github_trending.fetch_trending()
        except Exception as e:
            errors.append(f"trending: {e}")
        mentions = await hackernews.fetch_mentions()
        hn_names = {m["full_name"] for m in mentions}

        # 3. Track: snapshot toàn bộ repo theo dõi + ứng viên mới từ trending/HN
        await step("track", github_graphql.track(pool, extra_names=trending_names | hn_names))

        # 4. Gắn cờ trending + lưu mentions (sau track để repo mới đã có trong DB)
        stats["trending_flagged"] = await github_trending.apply_trending_flags(pool, trending_names)
        stats["hn_mentions_saved"] = await hackernews.save_mentions(pool, mentions)

        # 5. Phân loại (rule-based; chỉ repo chưa có nhãn để idempotent + nhanh)
        await step("categorize", categorize.categorize(pool, only_uncategorized=True))

        # 6. Ranking
        await step("rank", rank.rank(pool))

        # 7. AI Summary (tuỳ chọn)
        await step("summarize", summarize.summarize(pool))

        # 8. Invalidate cache
        stats["cache_invalidated"] = await invalidate_all()

        status = "partial" if errors else "success"
        await pool.execute(
            """UPDATE crawl_runs SET finished_at = now(), status = $1, stats = $2, error = $3
               WHERE id = $4""",
            status, json.dumps(stats, default=str), "\n".join(errors) or None, run_id,
        )
        summary_text = (
            f"{'✅' if status == 'success' else '⚠️'} AI Trend Radar [{status}] — "
            f"discover: {stats.get('discover', {}).get('accepted', '?')} repo mới, "
            f"track: {stats.get('track', {}).get('updated', '?')} cập nhật, "
            f"summaries: {stats.get('summarize', {}).get('summarized', 0)}"
        )
        log.info(summary_text)
        await _notify_slack(summary_text)
        return stats
    except Exception as e:
        await pool.execute(
            "UPDATE crawl_runs SET finished_at = now(), status = 'failed', error = $1 WHERE id = $2",
            f"{e}\n{traceback.format_exc()}", run_id,
        )
        await _notify_slack(f"❌ AI Trend Radar pipeline FAILED: {e}")
        raise
    finally:
        await release_pipeline_lock()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_daily(trigger="manual"))
