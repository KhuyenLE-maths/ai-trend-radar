import gzip
import json
from datetime import date

import pytest

from app.core.config import settings
from app.pipeline.raw_archive import RawArchive, read_records_tolerant, use_archive
from app.pipeline.steps import summarize

GEMINI = "generativelanguage.googleapis.com"
KEY = "gemini-SECRET"


def reply(text='{"tldr": "x"}'):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


@pytest.fixture
async def repos(pool, monkeypatch):
    for i in (1, 2, 3):
        await pool.execute(
            """INSERT INTO repositories (github_id, full_name, owner, name, url, hot_score)
               VALUES ($1,$2,'o','r','u',5)""", i, f"o/r{i}")
    monkeypatch.setattr(settings, "gemini_api_key", KEY)
    monkeypatch.setattr(settings, "summary_model", "gemini-3.8-flash")
    monkeypatch.setattr(summarize, "RATE_LIMIT_WAIT_SECONDS", 0)
    return pool


def gemini_calls(mock_http):
    return [r for r in mock_http.requests if GEMINI in str(r.url)]


async def test_summary_saved_with_gemini_model(repos, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "summary_daily_limit", 1)
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (200, reply())
    assert (await summarize.summarize(repos))["summarized"] == 1
    row = await repos.fetchrow("SELECT model, content FROM ai_summaries")
    assert row["model"] == "gemini-3.8-flash" and json.loads(row["content"]) == {"tldr": "x"}


async def test_request_shape(repos, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "summary_daily_limit", 1)
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (200, reply())
    await summarize.summarize(repos)
    [req] = gemini_calls(mock_http)
    body = json.loads(req.content)
    assert "/v1beta/models/gemini-3.8-flash:generateContent" in str(req.url)
    assert "o/r" in body["contents"][0]["parts"][0]["text"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"


async def test_key_only_in_header(repos, raw_dir, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "summary_daily_limit", 1)
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (200, reply())
    archive = RawArchive(raw_dir, 1, date(2026, 10, 31))
    with use_archive(archive):
        await summarize.summarize(repos)
    archive.close()
    [req] = gemini_calls(mock_http)
    assert req.headers["x-goog-api-key"] == KEY and KEY not in str(req.url)
    assert KEY not in "".join(gzip.open(p, "rt").read() for p in raw_dir.rglob("*.gz"))


async def test_response_recorded_raw(repos, raw_dir, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "summary_daily_limit", 1)
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (200, reply())
    archive = RawArchive(raw_dir, 1, date(2026, 10, 31))
    with use_archive(archive):
        await summarize.summarize(repos)
    [rec] = read_records_tolerant(raw_dir / "2026-10-31/run-1/gemini.jsonl.gz")
    assert rec["status"] == 200 and rec["body"] == reply()


@pytest.mark.parametrize("status,body", [
    (401, '{"error": {"code": "authentication"}}'),
    (403, '{"error": {"code": "permission_denied"}}'),
    (400, '{"error": {"details": [{"reason": "API_KEY_INVALID"}]}}'),
])
async def test_stops_on_invalid_key(repos, mock_http, status, body):
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (status, body)
    assert await summarize.summarize(repos) == {"summarized": 0, "failed": 1}
    assert len(gemini_calls(mock_http)) == 1


async def test_rate_limit_waits_then_stops(repos, mock_http):
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (429, "{}")
    assert await summarize.summarize(repos) == {"summarized": 0, "failed": 1}
    assert len(gemini_calls(mock_http)) == 2


async def test_overload_waits_then_stops(repos, mock_http):
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (503, "{}")
    assert await summarize.summarize(repos) == {"summarized": 0, "failed": 1}
    assert len(gemini_calls(mock_http)) == 2


@pytest.mark.parametrize("status", [429, 503])
async def test_rate_limit_recovers(repos, mock_http, monkeypatch, status):
    monkeypatch.setattr(settings, "summary_daily_limit", 1)
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (status, "{}")

    async def clear(_seconds):
        mock_http[GEMINI] = (200, reply())

    monkeypatch.setattr(summarize.asyncio, "sleep", clear)
    assert (await summarize.summarize(repos))["summarized"] == 1


async def test_blocked_prompt_skips_only_that_repo(repos, mock_http):
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (200, '{"promptFeedback": {"blockReason": "SAFETY"}}')
    assert await summarize.summarize(repos) == {"summarized": 0, "failed": 3}


async def test_server_error_skips_only_that_repo(repos, mock_http):
    mock_http["/readme"] = (200, "hello")
    mock_http[GEMINI] = (500, "down")
    assert await summarize.summarize(repos) == {"summarized": 0, "failed": 3}


async def test_no_key_skips_step(pool, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert await summarize.summarize(pool) == {"skipped": True}
