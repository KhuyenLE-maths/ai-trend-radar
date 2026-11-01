import httpx
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


class Routes(dict):
    def __init__(self):
        super().__init__()
        self.requests: list[httpx.Request] = []


@pytest.fixture
def mock_http(monkeypatch):
    """Thay httpx.AsyncClient: routes là {chuỗi con của URL: (status, body)}."""
    routes = Routes()
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        routes.requests.append(request)
        for key, (status, body) in routes.items():
            if key in str(request.url):
                return httpx.Response(status, text=body)
        return httpx.Response(404, text="no route")

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return routes
