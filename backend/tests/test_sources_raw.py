import gzip
from datetime import date
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.core.config import settings
from app.pipeline.raw_archive import RawArchive, read_records_tolerant, use_archive
from app.pipeline.sources import github_client, github_search, github_trending, hackernews
from app.pipeline.steps import summarize


@pytest.fixture
def archive(raw_dir):
    a = RawArchive(raw_dir, 1, date(2026, 10, 30))
    with use_archive(a):
        yield a


def records(raw_dir, source):
    return read_records_tolerant(raw_dir / f"2026-10-30/run-1/{source}.jsonl.gz")


def all_raw_text(raw_dir):
    return "".join(gzip.open(p, "rt").read() for p in raw_dir.rglob("*.gz"))


async def test_rest_get_records_error_responses(raw_dir, archive, mock_http):
    mock_http["/search"] = (404, "missing")
    with pytest.raises(httpx.HTTPStatusError):
        await github_client.rest_get("/search/repositories", {"q": "x"})
    [rec] = records(raw_dir, "github_rest")
    assert rec["status"] == 404 and rec["body"] == "missing"


async def test_token_never_in_raw_files(raw_dir, archive, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "github_token", "ghp_SECRET")
    mock_http["/graphql"] = (200, '{"data": {}}')
    mock_http["/readme"] = (200, "hello")
    mock_http["/search"] = (200, "{}")
    await github_client.rest_get("/search/repositories")
    await github_client.graphql("query {}")
    await github_client.fetch_readme_raw("o/r")
    archive.close()
    text = all_raw_text(raw_dir)
    assert "readme" in text and "ghp_SECRET" not in text


async def test_graphql_returns_partial_errors(mock_http):
    mock_http["/graphql"] = (200, '{"data": {"r0": null}, "errors": [{"type": "NOT_FOUND", "path": ["r0"]}]}')
    data, errors = await github_client.graphql("query {}")
    assert data == {"r0": None} and errors[0]["type"] == "NOT_FOUND"


async def test_trending_records_html_and_raises_when_all_fail(raw_dir, archive, mock_http):
    mock_http["github.com/trending"] = (500, "<html>down</html>")
    with pytest.raises(github_trending.TrendingUnavailable):
        await github_trending.fetch_trending()
    assert records(raw_dir, "github_trending")[0]["body"] == "<html>down</html>"


async def test_trending_partial_failure_still_returns_names(raw_dir, archive, mock_http):
    mock_http["trending?since"] = (200, '<article class="Box-row"><h2><a href="/o/r"></a></h2></article>')
    mock_http["github.com/trending"] = (500, "down")
    assert await github_trending.fetch_trending() == {"o/r"}


async def test_hackernews_failure_raises(raw_dir, archive, mock_http):
    mock_http["algolia"] = (500, "down")
    with pytest.raises(httpx.HTTPStatusError):
        await hackernews.fetch_mentions()
    assert records(raw_dir, "hackernews")[0]["status"] == 500


async def test_summarize_records_model_response(pool, raw_dir, archive, mock_http, monkeypatch):
    await pool.execute(
        """INSERT INTO repositories (github_id, full_name, owner, name, url, hot_score)
           VALUES (1,'o/r','o','r','u',5)""")
    mock_http["/readme"] = (200, "hello")
    msg = SimpleNamespace(
        content=[SimpleNamespace(text='{"tldr": "x"}')], model_dump_json=lambda: '{"id": "msg_1"}')

    async def create(**kw):
        return msg

    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(
        anthropic, "AsyncAnthropic",
        lambda api_key: SimpleNamespace(messages=SimpleNamespace(create=create)))
    await summarize.summarize(pool)
    assert records(raw_dir, "anthropic")[0]["body"] == '{"id": "msg_1"}'


async def test_check_github_token_401_raises(mock_http):
    mock_http["/rate_limit"] = (401, "bad")
    with pytest.raises(github_client.GitHubAuthError, match="GITHUB_TOKEN"):
        await github_client.check_github_token()


async def test_check_github_token_empty_raises(mock_http, monkeypatch):
    monkeypatch.setattr(settings, "github_token", "")
    with pytest.raises(github_client.GitHubAuthError):
        await github_client.check_github_token()


async def test_check_github_token_ok(mock_http):
    mock_http["/rate_limit"] = (200, "{}")
    await github_client.check_github_token()


async def test_discover_counts_failed_queries(pool, mock_http, monkeypatch):
    monkeypatch.setattr(settings, "discover_pages_per_query", 1)
    monkeypatch.setattr(github_search, "TOPICS", ["llm"])
    mock_http["/search"] = (404, "x")
    result = await github_search.discover(pool)
    assert result["failed_queries"] == 2 and result["scanned"] == 0
