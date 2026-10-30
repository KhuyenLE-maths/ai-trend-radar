"""Worker process: kiểm tra mỗi 15 phút xem hôm nay đã crawl chưa.

Một vòng kiểm tra dùng chung cho crawl đúng giờ, chạy bù khi máy tắt/ngủ qua
giờ crawl, và thử lại khi crawl lỗi. Lịch lấy từ PIPELINE_CRON (UTC).

Chạy: python -m app.pipeline.scheduler
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.cache import get_redis
from app.core.config import settings
from app.core.db import get_pool, init_db
from app.pipeline.run_daily import run_daily

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler")

TICK_MINUTES = 15
RETRY_MINUTES = 60
MAX_FAILED_PER_DAY = 3


@dataclass
class RunInfo:
    status: str
    started_at: datetime
    finished_at: datetime | None
    failure_kind: str | None


def should_run(now: datetime, due_at: datetime, today_runs: list[RunInfo]) -> bool:
    if now < due_at:
        return False
    if any(r.status in ("running", "success", "partial") for r in today_runs):
        return False
    failed = [r for r in today_runs if r.status == "failed"]
    if any(r.failure_kind == "auth" for r in failed) or len(failed) >= MAX_FAILED_PER_DAY:
        return False
    last = max((r.finished_at or r.started_at for r in failed), default=None)
    return last is None or now - last >= timedelta(minutes=RETRY_MINUTES)


def due_time(now: datetime) -> datetime:
    """Lần kích hoạt đầu tiên của cron trong ngày UTC hiện tại."""
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    trigger = CronTrigger.from_crontab(settings.pipeline_cron, timezone="UTC")
    return trigger.get_next_fire_time(None, day_start)


async def reap_stale_runs(pool) -> int:
    """Lock còn giữ nghĩa là crawl đang chạy thật (có thể ở API) — không đụng tới."""
    if await get_redis().exists("pipeline:lock"):
        return 0
    res = await pool.execute(
        """UPDATE crawl_runs SET status = 'failed', finished_at = now(),
             error = concat_ws(E'\n', error, 'Tiến trình dừng giữa chừng, lần chạy được dọn tự động.')
           WHERE status = 'running'"""
    )
    return int(res.split()[-1])


async def tick() -> None:
    pool = await get_pool()
    reaped = await reap_stale_runs(pool)
    if reaped:
        log.warning("Đã dọn %s lần chạy kẹt", reaped)
    now = datetime.now(timezone.utc)
    rows = await pool.fetch(
        """SELECT status, started_at, finished_at, failure_kind FROM crawl_runs
           WHERE started_at >= $1""",
        now.replace(hour=0, minute=0, second=0, microsecond=0),
    )
    if should_run(now, due_time(now), [RunInfo(**dict(r)) for r in rows]):
        await run_daily(trigger="schedule")


async def main() -> None:
    await init_db()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        tick,
        IntervalTrigger(minutes=TICK_MINUTES, timezone="UTC"),
        id="tick",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=None,
        next_run_time=datetime.now(timezone.utc),  # kiểm tra ngay khi khởi động
    )
    scheduler.start()
    log.info("Scheduler started — kiểm tra mỗi %s phút, cron: %s (UTC)", TICK_MINUTES, settings.pipeline_cron)
    await asyncio.Event().wait()  # giữ process sống


if __name__ == "__main__":
    asyncio.run(main())
