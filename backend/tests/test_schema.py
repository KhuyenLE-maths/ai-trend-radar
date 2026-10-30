from app.core.db import init_db


async def test_new_tables_exist(pool):
    names = {r["table_name"] for r in await pool.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}
    assert {"repo_run_snapshots", "raw_archives"} <= names


async def test_failure_kind_column(pool):
    assert await pool.fetchval(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='crawl_runs' AND column_name='failure_kind'") == 1


async def test_init_db_idempotent(pool):
    await init_db()
    await init_db()
