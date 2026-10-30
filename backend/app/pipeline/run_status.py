"""Quyết định trạng thái lần crawl từ kết quả các bước."""

PARTIAL_STEPS = {"discover", "trending", "hn", "categorize", "rank", "run_snapshots"}


def classify_run(stats: dict, failed_steps: set[str], raw_error: str | None) -> str:
    if raw_error or "track" in failed_steps:
        return "failed"
    track = stats.get("track") or {}
    updated = track.get("updated", 0)
    attempted = updated + track.get("failed", 0)  # repo đã xoá không tính
    ratio = updated / attempted if attempted else 0
    if ratio < 0.5:
        return "failed"
    if ratio < 0.95 or failed_steps & PARTIAL_STEPS:
        return "partial"
    return "success"
