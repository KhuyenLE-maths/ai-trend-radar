import pytest

from app.core import cache
from app.core.config import settings
from app.pipeline import run_daily as mod
from app.pipeline.raw_archive import record_raw
from app.pipeline.sources.github_client import GitHubAuthError


@pytest.fixture
def calls(pool, raw_dir, monkeypatch):
    """Giả lập mọi nguồn và bước ngoài; ghi lại bước nào đã chạy."""
    log: list[str] = []

    def stub(target, attr, result):
        async def _stub(*a, **kw):
            log.append(attr)
            return result
        monkeypatch.setattr(target, attr, _stub)

    async def track(pool, extra_names=None):
        log.append("track")
        record_raw("github_graphql", {"url": "/graphql"}, 200, "{}")
        await pool.execute("UPDATE repositories SET last_crawled_at = now()")
        return {"updated": 1, "failed": 0, "deleted": 0}

    stub(mod, "check_github_token", None)
    stub(mod.github_search, "discover", {"scanned": 1, "accepted": 1, "failed_queries": 0})
    stub(mod.github_trending, "fetch_trending", {"o/r"})
    stub(mod.github_trending, "apply_trending_flags", 1)
    stub(mod.hackernews, "fetch_mentions", [])
    stub(mod.hackernews, "save_mentions", 0)
    stub(mod.categorize, "categorize", {})
    stub(mod.rank, "rank", {})
    stub(mod.summarize, "summarize", {"summarized": 0})
    monkeypatch.setattr(mod.github_graphql, "track", track)
    return log


async def insert_repo(pool):
    await pool.execute(
        """INSERT INTO repositories (github_id, full_name, owner, name, url, stars)
           VALUES (1,'o/r','o','r','u',7)""")


async def last_run(pool):
    return await pool.fetchrow("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 1")


async def test_bad_token_stops_run(pool, calls, monkeypatch):
    async def bad():
        raise GitHubAuthError("GITHUB_TOKEN không hợp lệ")
    monkeypatch.setattr(mod, "check_github_token", bad)
    await mod.run_daily()
    run = await last_run(pool)
    assert run["status"] == "failed" and run["failure_kind"] == "auth"
    assert "GITHUB_TOKEN" in run["error"]
    assert run["finished_at"] is not None
    assert "discover" not in calls
    assert await cache.acquire_pipeline_lock()


async def test_failed_track_skips_later_steps(pool, calls, monkeypatch):
    async def track(pool, extra_names=None):
        return {"updated": 0, "failed": 100, "deleted": 0}
    monkeypatch.setattr(mod.github_graphql, "track", track)
    await mod.run_daily()
    assert (await last_run(pool))["status"] == "failed"
    assert not {"rank", "apply_trending_flags", "summarize"} & set(calls)


async def test_two_runs_same_day_keep_separate_history(pool, calls, raw_dir):
    await insert_repo(pool)
    await mod.run_daily()
    await mod.run_daily()
    assert await pool.fetchval("SELECT count(*) FROM crawl_runs WHERE status='success'") == 2
    assert await pool.fetchval("SELECT count(*) FROM repo_run_snapshots") == 2
    assert await pool.fetchval("SELECT stars FROM repo_run_snapshots LIMIT 1") == 7
    paths = [r["path"] for r in await pool.fetch("SELECT path FROM raw_archives ORDER BY run_id")]
    assert len(paths) == 2 and paths[0] != paths[1]
    assert all((raw_dir / p).exists() for p in paths)


async def test_snapshots_only_for_repos_updated_this_run(pool, calls, monkeypatch):
    await insert_repo(pool)

    async def track(pool, extra_names=None):
        return {"updated": 1, "failed": 0, "deleted": 0}
    monkeypatch.setattr(mod.github_graphql, "track", track)
    await mod.run_daily()
    assert await pool.fetchval("SELECT count(*) FROM repo_run_snapshots") == 0


async def test_raw_write_failure_marks_run_failed(pool, calls, tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "raw_data_dir", str(blocker))
    await mod.run_daily()
    run = await last_run(pool)
    assert run["status"] == "failed" and "thô" in run["error"]


async def test_locked_run_creates_no_row(pool, calls):
    await cache.acquire_pipeline_lock()
    assert await mod.run_daily() == {"skipped": "locked"}
    assert await pool.fetchval("SELECT count(*) FROM crawl_runs") == 0


async def test_init_failure_releases_lock(pool, calls, monkeypatch):
    async def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(mod, "init_db", boom)
    with pytest.raises(RuntimeError):
        await mod.run_daily()
    assert await cache.acquire_pipeline_lock()


async def test_trending_failure_keeps_flags_and_is_partial(pool, calls, monkeypatch):
    async def down():
        raise mod.github_trending.TrendingUnavailable("x")
    monkeypatch.setattr(mod.github_trending, "fetch_trending", down)
    await mod.run_daily()
    assert (await last_run(pool))["status"] == "partial"
    assert "apply_trending_flags" not in calls


async def test_unexpected_crash_is_failed(pool, calls, monkeypatch):
    async def boom(*a):
        raise RuntimeError("boom")
    monkeypatch.setattr(mod.hackernews, "save_mentions", boom)
    await mod.run_daily()
    run = await last_run(pool)
    assert run["status"] == "failed" and "boom" in run["error"]
