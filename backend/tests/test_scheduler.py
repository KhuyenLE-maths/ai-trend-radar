from datetime import datetime, timezone

from app.core import cache
from app.pipeline import scheduler
from app.pipeline.scheduler import RunInfo, due_time, reap_stale_runs, should_run

D = datetime(2026, 10, 30, 2, 0, tzinfo=timezone.utc)


def at(h, m=0):
    return D.replace(hour=h, minute=m)


def run(status, h, kind=None):
    return RunInfo(status, at(h), at(h), kind)


def test_before_due_no_run():
    assert not should_run(at(1), D, [])


def test_after_due_runs():
    assert should_run(at(5), D, [])


def test_success_done():
    assert not should_run(at(5), D, [run("success", 3)])


def test_partial_done():
    assert not should_run(at(5), D, [run("partial", 3)])


def test_running_blocks():
    assert not should_run(at(5), D, [RunInfo("running", at(4), None, None)])


def test_failed_retries_after_hour():
    assert not should_run(at(3, 30), D, [run("failed", 3)])
    assert should_run(at(4), D, [run("failed", 3)])


def test_three_failures_stop():
    assert not should_run(at(9), D, [run("failed", 3), run("failed", 5), run("failed", 7)])


def test_auth_failure_not_retried():
    assert not should_run(at(9), D, [run("failed", 3, "auth")])


def test_failed_without_finish_time_uses_started_at():
    assert should_run(at(5), D, [RunInfo("failed", at(3), None, None)])


def test_due_time_is_first_cron_fire_of_utc_day():
    assert due_time(at(20)) == D


async def test_reap_marks_stale_run_failed(pool):
    await pool.execute("INSERT INTO crawl_runs (status) VALUES ('running')")
    assert await reap_stale_runs(pool) == 1
    row = await pool.fetchrow("SELECT * FROM crawl_runs")
    assert row["status"] == "failed" and row["finished_at"] is not None and "dừng" in row["error"]


async def test_reap_keeps_run_when_lock_held(pool):
    await pool.execute("INSERT INTO crawl_runs (status) VALUES ('running')")
    await cache.acquire_pipeline_lock()
    assert await reap_stale_runs(pool) == 0
    assert await pool.fetchval("SELECT status FROM crawl_runs") == "running"


async def test_tick_twice_runs_once(pool, monkeypatch):
    calls = []

    async def fake_run(trigger):
        calls.append(trigger)
        await pool.execute("INSERT INTO crawl_runs (status, finished_at) VALUES ('success', now())")

    monkeypatch.setattr(scheduler, "run_daily", fake_run)
    monkeypatch.setattr(scheduler, "due_time", lambda now: now.replace(hour=0, minute=0))
    await scheduler.tick()
    await scheduler.tick()
    assert calls == ["schedule"]
