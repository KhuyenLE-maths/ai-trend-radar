"""Orchestrator pipeline hàng ngày (mục 8.2).

Thứ tự: discover → track → trending flags → mentions → categorize → rank
        → summarize → invalidate cache → notify.
Mỗi bước fail-soft: lỗi được ghi vào crawl_runs.stats, các bước sau vẫn chạy
nếu không phụ thuộc cứng. Token hỏng, track thất bại hoặc không ghi được dữ liệu
thô thì dừng sớm. Redis lock chống chạy chồng.
"""
import asyncio
import contextlib
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path

import httpx

from app.core.cache import (
    acquire_pipeline_lock, invalidate_all, release_pipeline_lock, renew_pipeline_lock,
)
from app.core.config import settings
from app.core.db import get_pool, init_db
from app.pipeline.raw_archive import RawArchive, use_archive
from app.pipeline.run_status import classify_run
from app.pipeline.sources import github_graphql, github_search, github_trending, hackernews
from app.pipeline.sources.github_client import GitHubAuthError, check_github_token
from app.pipeline.steps import categorize, rank, summarize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")

LOCK_HEARTBEAT_SECONDS = 300


async def _notify_slack(text: str) -> None:
    if not settings.slack_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.slack_webhook_url, json={"text": text})
    except Exception as e:
        log.warning("slack notify fail: %s", e)


SAVE_RUN_SNAPSHOTS_SQL = """
INSERT INTO repo_run_snapshots (
  run_id, repo_id, stars, forks, watchers, open_issues, contributors,
  star_growth_7d, star_growth_30d, hot_score, trending_flag
)
SELECT $1, id, stars, forks, watchers, open_issues, contributors,
       star_growth_7d, star_growth_30d, hot_score, trending_flag
FROM repositories WHERE last_crawled_at >= $2
"""


class _StopRun(Exception):
    """Dừng lần crawl sớm; trạng thái do classify_run quyết định."""


async def save_run_snapshots(pool, run_id: int, started_at: datetime) -> int:
    """Chỉ ghi repo thực sự được cập nhật trong lần này, không ghi số cũ."""
    res = await pool.execute(SAVE_RUN_SNAPSHOTS_SQL, run_id, started_at)
    return int(res.split()[-1])


async def _pipeline(pool, run_id: int, started_at: datetime, archive: RawArchive,
                    stats: dict, errors: list[str], failed_steps: set[str]) -> None:
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
            failed_steps.add(name)
        if archive.error:
            raise _StopRun

    await check_github_token()

    # 1. Discover repo mới qua Search API
    await step("discover", github_search.discover(pool))
    discovered = stats["discover"]
    if discovered.get("failed_queries") and not discovered.get("scanned"):
        errors.append("discover: mọi truy vấn đều lỗi")
        failed_steps.add("discover")

    # 2. Tín hiệu ngoài: trending + HN (fail-soft, có thể rỗng)
    trending_names: set[str] = set()
    try:
        trending_names = await github_trending.fetch_trending()
    except Exception as e:
        errors.append(f"trending: {e}")
        failed_steps.add("trending")
    mentions: list[dict] = []
    try:
        mentions = await hackernews.fetch_mentions()
    except Exception as e:
        errors.append(f"hn: {e}")
        failed_steps.add("hn")
    hn_names = {m["full_name"] for m in mentions}

    # 3. Track: snapshot toàn bộ repo theo dõi + ứng viên mới từ trending/HN
    await step("track", github_graphql.track(pool, extra_names=trending_names | hn_names))
    if classify_run(stats, failed_steps, archive.error) == "failed":
        errors.append(f"track: cập nhật quá ít repo ({stats['track']})")
        raise _StopRun

    # 4. Gắn cờ trending + lưu mentions (sau track để repo mới đã có trong DB)
    if "trending" not in failed_steps:  # trending lỗi thì giữ cờ cũ, không xoá hết
        stats["trending_flagged"] = await github_trending.apply_trending_flags(pool, trending_names)
    stats["hn_mentions_saved"] = await hackernews.save_mentions(pool, mentions)

    # 5. Phân loại (rule-based; chỉ repo chưa có nhãn để idempotent + nhanh)
    await step("categorize", categorize.categorize(pool, only_uncategorized=True))

    # 6. Ranking + lưu lịch sử của lần crawl này
    await step("rank", rank.rank(pool))
    await step("run_snapshots", save_run_snapshots(pool, run_id, started_at))

    # 7. AI Summary (tuỳ chọn)
    await step("summarize", summarize.summarize(pool))
    summary = stats["summarize"]
    if summary.get("failed") and not summary.get("summarized"):
        errors.append(f"summarize: mọi lần tóm tắt đều lỗi ({summary['failed']})")
        failed_steps.add("summarize")

    # 8. Invalidate cache
    stats["cache_invalidated"] = await invalidate_all()


async def _run(trigger: str) -> dict:
    await init_db()
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO crawl_runs (status, trigger) VALUES ('running', $1) RETURNING id, started_at", trigger
    )
    run_id, started_at = row["id"], row["started_at"]
    archive = RawArchive(Path(settings.raw_data_dir), run_id, started_at.date())
    stats: dict = {}
    errors: list[str] = []
    failed_steps: set[str] = set()
    failure_kind = None
    crashed = False

    with use_archive(archive):
        try:
            await _pipeline(pool, run_id, started_at, archive, stats, errors, failed_steps)
        except _StopRun:
            pass
        except GitHubAuthError as e:
            failure_kind = "auth"
            errors.append(str(e))
        except Exception as e:
            crashed = True
            errors.append(f"{e}\n{traceback.format_exc()}")

    files = archive.close()
    for f in files:
        await pool.execute(
            """INSERT INTO raw_archives (run_id, source, path, line_count, byte_size, sha256)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            run_id, f.source, f.path, f.line_count, f.byte_size, f.sha256,
        )
    if archive.error:
        errors.append(f"không ghi được dữ liệu thô: {archive.error}")

    status = "failed" if crashed else classify_run(stats, failed_steps, archive.error)
    await pool.execute(
        """UPDATE crawl_runs SET finished_at = now(), status = $1, stats = $2, error = $3,
                                 failure_kind = $4
           WHERE id = $5""",
        status, json.dumps(stats, default=str), "\n".join(errors) or None, failure_kind, run_id,
    )
    icon = {"success": "✅", "partial": "⚠️"}.get(status, "❌")
    summary_text = (
        f"{icon} AI Trend Radar [{status}] — "
        f"discover: {stats.get('discover', {}).get('accepted', '?')} repo mới, "
        f"track: {stats.get('track', {}).get('updated', '?')} cập nhật, "
        f"summaries: {stats.get('summarize', {}).get('summarized', 0)}"
    )
    log.info(summary_text)
    await _notify_slack(summary_text)
    return stats


async def _keep_lock() -> None:
    while True:
        await asyncio.sleep(LOCK_HEARTBEAT_SECONDS)
        try:
            await renew_pipeline_lock()
        except Exception as e:
            log.warning("không gia hạn được lock: %s", e)


async def run_daily(trigger: str = "cron") -> dict:
    if not await acquire_pipeline_lock():
        log.warning("Pipeline đang chạy (lock tồn tại) — bỏ qua lần trigger này.")
        return {"skipped": "locked"}
    heartbeat = asyncio.create_task(_keep_lock())
    try:
        return await _run(trigger)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await release_pipeline_lock()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_daily(trigger="manual"))
