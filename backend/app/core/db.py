import pathlib

import asyncpg

from app.core.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_db() -> None:
    """Tạo schema + seed categories (idempotent — chạy mỗi lần khởi động)."""
    pool = await get_pool()
    base = pathlib.Path(__file__).resolve().parent.parent / "db"
    async with pool.acquire() as conn:
        await conn.execute((base / "schema.sql").read_text())
        await conn.execute((base / "seed.sql").read_text())
