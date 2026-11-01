import pytest

from app.pipeline.run_status import classify_run


@pytest.mark.parametrize("updated,failed,expected", [
    (0, 3063, "failed"), (0, 0, "failed"), (49, 51, "failed"),
    (50, 50, "partial"), (94, 6, "partial"), (95, 5, "success"), (100, 0, "success"),
])
def test_track_thresholds(updated, failed, expected):
    assert classify_run({"track": {"updated": updated, "failed": failed}}, set(), None) == expected


def test_deleted_repos_do_not_count():
    assert classify_run({"track": {"updated": 95, "failed": 0, "deleted": 40}}, set(), None) == "success"


@pytest.mark.parametrize("step", ["discover", "trending", "hn", "categorize", "rank", "summarize"])
def test_step_failure_is_partial(step):
    assert classify_run({"track": {"updated": 10, "failed": 0}}, {step}, None) == "partial"


def test_summary_failure_is_not_a_failure():
    stats = {"track": {"updated": 10, "failed": 0}, "summarize": {"failed": 3}}
    assert classify_run(stats, set(), None) == "success"


def test_raw_error_is_failed():
    assert classify_run({"track": {"updated": 10, "failed": 0}}, set(), "disk full") == "failed"


def test_track_exception_is_failed():
    assert classify_run({"track": {"error": "x"}}, {"track"}, None) == "failed"
