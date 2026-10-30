from datetime import datetime

from app.pipeline.sources import github_graphql


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


def fake_graphql(nodes_by_name, seen=None):
    async def _graphql(query):
        out = {}
        for i, name in enumerate(n for n in _names(query)):
            if seen is not None:
                seen.append(name)
            out[f"r{i}"] = nodes_by_name.get(name)
        return out
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
    assert len(seen) == 60 and "o/r1" in seen


async def test_bad_node_only_fails_that_repo(pool, monkeypatch):
    await insert_repo(pool, 1)
    await insert_repo(pool, 2)
    nodes = {"o/r1": make_node(1, "o/r1", createdAt="garbage"), "o/r2": make_node(2, "o/r2")}
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql(nodes))
    result = await github_graphql.track(pool)
    assert result["updated"] == 1 and result["failed"] == 1


async def test_missing_repo_counts_as_deleted_not_failed(pool, monkeypatch):
    await insert_repo(pool, 1)
    monkeypatch.setattr(github_graphql, "graphql", fake_graphql({}))
    result = await github_graphql.track(pool)
    assert result["deleted"] == 1 and result["failed"] == 0
