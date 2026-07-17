import asyncio

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import settings
from app.core.db import get_pool

router = APIRouter(tags=["admin"])


def _check(token: str | None):
    if token != settings.admin_token:
        raise HTTPException(401, "Invalid admin token")


@router.post("/admin/crawl")
async def trigger_crawl(x_admin_token: str | None = Header(None)):
    """Chạy pipeline thủ công (nền). Redis lock chống chạy chồng với cron."""
    _check(x_admin_token)
    from app.pipeline.run_daily import run_daily  # import trễ, tránh vòng lặp

    asyncio.create_task(run_daily(trigger="manual"))
    return {"status": "started", "note": "Theo dõi tiến độ qua GET /api/v1/admin/runs"}


@router.get("/admin/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100), x_admin_token: str | None = Header(None)):
    _check(x_admin_token)
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, started_at, finished_at, trigger, status, stats, error FROM crawl_runs ORDER BY id DESC LIMIT $1",
        limit,
    )
    return {"data": [dict(x) for x in rows]}
