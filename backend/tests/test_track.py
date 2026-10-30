from datetime import datetime

import httpx

from app.pipeline.sources import github_graphql
from app.pipeline.sources.github_client import GitHubError, GitHubRateLimited


def make_node(database_id, name, **overrides):
    node = {
        "databaseId": database_id, "nameWithOwner": name, "description": "llm agent",
        "stargazerCount": 10, "forkCount": 2, "watchers": {"totalCount": 3},
        "issues": {"totalCount": 4}, "mentionableUsers": {"totalCount": 5},
        "primaryLanguage": {"name": "Python"}, "licenseInfo": {"spdxId": "MIT"},
        "repositoryTopics": {"nodes": [{"topic": {"name": "llm"}}]},
        "pushedAt": "2026-10-01T00:00:00Z", "createdAt": "2026-01-01T00:00:00Z",
        "isArchived": False, "isFork": False, "homepageUrl": None,
        "owner": {"avatarUrl": None, "login": name.split("/")[0]},
        "defaultBranchRef": {"target": {"committedDate": "2026-10-02T00:00:00Z"}},
    }
    return {**node, **overrides}


async def insert_repo(pool, i, archived=False):
    await pool.execute(
        """INSERT INTO repositories (github_id, full_name, owner, name, url, is_archived, stars)
           VALUES ($1,$2,'o',$3,'u',$4,$5)""",
        i, f"o/r{i}", f"r{i}", archived, 1000 - i,
    )


def fake_graphql(nodes_by_name, seen=None, errors_for=None):
    """errors_for(name, batch_size) trả type lỗi GraphQL của repo, hoặc None."""
    async def _graphql(query):
        names = _names(query)
        data, errors = {}, []
        for i, name in enumerate(names):
            if seen is not None:
                seen.append(name)
            error = errors_for(name, len(names)) if errors_for else None
            data[f"r{i}"] = None if error else nodes_by_name.get(name)
            if error:
                errors.append({"type": error, "path": [f"r{i}"]})
        return data, errors
    return _graphql


def _names(query):
    import re
    return [f"{o}/{n}" for o, n in re.findall(r'repository\(owner: "([^"]+)", name: "([^"]+)"\)', query)]


async def test_track_writes_repo_and_snapshot(pool, monkeypatch):
    await insert_repo(pool, 1)
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql({"o/r1": make_node(1, "o/r1")}))
    result = await github_graphql.track(pool)
    assert result["updated"] == 1 and result["snapshots"] == 1
    assert isinstance(await pool.fetchval("SELECT repo_pushed_at FROM repositories"), datetime)
    assert await pool.fetchval("SELECT count(*) FROM repo_snapshots") == 1


async def test_track_includes_archived_repos_without_cap(pool, monkeypatch):
    for i in range(1, 61):
        await insert_repo(pool, i, archived=i == 1)
    seen = []
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql({}, seen))
    await github_graphql.track(pool)
    assert len(set(seen)) == 60 and "o/r1" in seen


async def test_bad_node_only_fails_that_repo(pool, monkeypatch):
    await insert_repo(pool, 1)
    await insert_repo(pool, 2)
    nodes = {"o/r1": make_node(1, "o/r1", createdAt="garbage"), "o/r2": make_node(2, "o/r2")}
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql(nodes))
    result = await github_graphql.track(pool)
    assert result["updated"] == 1 and result["failed"] == 1


async def test_not_found_counts_as_deleted(pool, monkeypatch):
    await insert_repo(pool, 1)
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql({}, errors_for=lambda n, size: "NOT_FOUND"))
    result = await github_graphql.track(pool)
    assert result["deleted"] == 1 and result["failed"] == 0


async def test_resource_limit_is_retried_in_smaller_batches(pool, monkeypatch):
    for i in range(1, 5):
        await insert_repo(pool, i)
    nodes = {f"o/r{i}": make_node(i, f"o/r{i}") for i in range(1, 5)}
    errors = lambda n, size: "RESOURCE_LIMITS_EXCEEDED" if size > 1 else None
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql(nodes, errors_for=errors))
    result = await github_graphql.track(pool)
    assert result["updated"] == 4 and result["deleted"] == 0 and result["failed"] == 0


async def test_persistent_resource_limit_is_failed_not_deleted(pool, monkeypatch):
    await insert_repo(pool, 1)
    await insert_repo(pool, 2)
    errors = lambda n, size: "RESOURCE_LIMITS_EXCEEDED"
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql({}, errors_for=errors))
    result = await github_graphql.track(pool)
    assert result["failed"] == 2 and result["deleted"] == 0


async def test_server_error_is_retried_in_smaller_batches(pool, monkeypatch):
    await insert_repo(pool, 1)
    await insert_repo(pool, 2)
    nodes = {"o/r1": make_node(1, "o/r1"), "o/r2": make_node(2, "o/r2")}
    inner = fake_graphql(nodes)

    async def flaky(query):
        if len(_names(query)) > 1:
            raise GitHubError("graphql retryable 502")
        return await inner(query)

    monkeypatch.setattr(github_graphql, "graphql", flaky)
    assert (await github_graphql.track(pool))["updated"] == 2


async def test_rate_limit_is_not_split(pool, monkeypatch):
    await insert_repo(pool, 1)
    await insert_repo(pool, 2)
    calls = []

    async def limited(query):
        calls.append(query)
        raise GitHubRateLimited("graphql rate limited 403")

    monkeypatch.setattr(github_graphql, "graphql", limited)
    result = await github_graphql.track(pool)
    assert len(calls) == 1 and result["failed"] == 2


async def test_transport_error_is_not_split(pool, monkeypatch):
    await insert_repo(pool, 1)
    await insert_repo(pool, 2)
    calls = []

    async def down(query):
        calls.append(query)
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(github_graphql, "graphql", down)
    result = await github_graphql.track(pool)
    assert len(calls) == 1 and result["failed"] == 2


async def test_track_gives_up_after_consecutive_empty_batches(pool, monkeypatch):
    for i in range(1, 201):
        await insert_repo(pool, i)
    calls = []

    async def down(query):
        calls.append(query)
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(github_graphql, "graphql", down)
    result = await github_graphql.track(pool)
    assert len(calls) == github_graphql.MAX_EMPTY_BATCHES
    assert result["failed"] == 200 and result["updated"] == 0
