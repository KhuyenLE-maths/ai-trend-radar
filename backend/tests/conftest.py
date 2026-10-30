import pytest

from app.core import cache, db
from app.core.config import settings

TABLES = (
    "raw_archives, repo_run_snapshots, repo_snapshots, repo_mentions, ai_summaries, "
    "repo_categories, repo_tags, raw_items, crawl_runs, repositories"
)


@pytest.fixture
async def pool():
    """Pool thật, schema đã khởi tạo, dữ liệu sạch cho từng test."""
    db._pool = None
    cache._redis = None
    await db.init_db()
    p = await db.get_pool()
    await p.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    await cache.release_pipeline_lock()
    yield p
    await cache.get_redis().aclose()
    cache._redis = None
    await db.close_pool()


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    path = tmp_path / "raw"
    path.mkdir()
    monkeypatch.setattr(settings, "raw_data_dir", str(path))
    return path
