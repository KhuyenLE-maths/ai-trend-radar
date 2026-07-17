"""Worker process: APScheduler chạy pipeline theo cron (mục 8.1).

Chạy: python -m app.pipeline.scheduler
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.pipeline.run_daily import run_daily

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler")


async def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_daily,
        CronTrigger.from_crontab(settings.pipeline_cron, timezone="UTC"),
        id="run_daily",
        max_instances=1,          # APScheduler-level; Redis lock là tầng bảo vệ thứ 2
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("Scheduler started — cron: %s (UTC)", settings.pipeline_cron)

    if settings.run_on_start:
        log.info("RUN_ON_START=true → chạy pipeline ngay...")
        try:
            await run_daily(trigger="startup")
        except Exception as e:
            log.error("Pipeline khởi động fail: %s", e)

    await asyncio.Event().wait()  # giữ process sống


if __name__ == "__main__":
    asyncio.run(main())
