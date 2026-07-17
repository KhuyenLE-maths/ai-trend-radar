"""Track: snapshot metrics hàng ngày cho mọi repo đang theo dõi qua GraphQL (batch)."""
import json
import logging

import asyncpg

from app.core.config import settings
from app.pipeline.sources.github_client import graphql
from app.pipeline.steps.filter_ai import relevance_score

log = logging.getLogger("pipeline.track")

BATCH = 50

FRAGMENT = """
  databaseId nameWithOwner description stargazerCount forkCount
  watchers { totalCount } issues(states: OPEN) { totalCount }
  mentionableUsers { totalCount }
  primaryLanguage { name } licenseInfo { spdxId }
  repositoryTopics(first: 20) { nodes { topic { name } } }
  pushedAt createdAt isArchived isFork homepageUrl
  owner { avatarUrl login }
  defaultBranchRef { target { ... on Commit { committedDate } } }
"""

UPSERT_SQL = """
INSERT INTO repositories (
  github_id, full_name, owner, name, url, homepage, description, logo_url,
  language, license_spdx, topics, is_archived, is_fork,
  stars, forks, watchers, open_issues, contributors,
  repo_created_at, repo_pushed_at, last_commit_at, ai_relevance, last_crawled_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
          $19::timestamptz,$20::timestamptz,$21::timestamptz,$22, now())
ON CONFLICT (github_id) DO UPDATE SET
  full_name = EXCLUDED.full_name, owner = EXCLUDED.owner, name = EXCLUDED.name,
  url = EXCLUDED.url, homepage = EXCLUDED.homepage, description = EXCLUDED.description,
  logo_url = EXCLUDED.logo_url, language = EXCLUDED.language,
  license_spdx = EXCLUDED.license_spdx, topics = EXCLUDED.topics,
  is_archived = EXCLUDED.is_archived, is_fork = EXCLUDED.is_fork,
  stars = EXCLUDED.stars, forks = EXCLUDED.forks, watchers = EXCLUDED.watchers,
  open_issues = EXCLUDED.open_issues, contributors = EXCLUDED.contributors,
  repo_pushed_at = EXCLUDED.repo_pushed_at, last_commit_at = EXCLUDED.last_commit_at,
  last_crawled_at = now()
RETURNING id
"""

SNAPSHOT_SQL = """
INSERT INTO repo_snapshots (repo_id, snapshot_date, stars, forks, watchers, open_issues, contributors)
VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6)
ON CONFLICT (repo_id, snapshot_date) DO UPDATE SET
  stars = EXCLUDED.stars, forks = EXCLUDED.forks, watchers = EXCLUDED.watchers,
  open_issues = EXCLUDED.open_issues, contributors = EXCLUDED.contributors
"""


def _build_query(names: list[str]) -> str:
    parts = []
    for i, fn in enumerate(names):
        owner, _, name = fn.partition("/")
        parts.append(
            f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {FRAGMENT} }}'
        )
    return "query {\n" + "\n".join(parts) + "\n}"


async def _select_tracked(pool: asyncpg.Pool) -> list[str]:
    rows = await pool.fetch(
        """SELECT full_name FROM repositories WHERE NOT is_archived
           ORDER BY hot_score DESC NULLS LAST, stars DESC LIMIT $1""",
        settings.max_tracked_repos,
    )
    return [r["full_name"] for r in rows]


async def track(pool: asyncpg.Pool, extra_names: set[str] | None = None) -> dict:
    """Fetch metrics cho repo trong DB + các ứng viên ngoài (trending/HN).
    Repo mới (chưa có trong DB) phải vượt ngưỡng AI-relevance mới được nhận."""
    names = await _select_tracked(pool)
    known = {n.lower() for n in names}
    for n in extra_names or set():
        if n.lower() not in known:
            names.append(n)

    updated = snapshots = rejected = failed = 0
    async with pool.acquire() as conn:
        for i in range(0, len(names), BATCH):
            batch = names[i : i + BATCH]
            try:
                data = await graphql(_build_query(batch))
            except Exception as e:
                log.warning("graphql batch %s fail: %s", i // BATCH, e)
                failed += len(batch)
                continue
            for j, fn in enumerate(batch):
                node = data.get(f"r{j}")
                if not node or node.get("databaseId") is None:
                    continue  # repo bị xoá/private — giữ bản ghi cũ
                topics = [t["topic"]["name"].lower() for t in node["repositoryTopics"]["nodes"]]
                desc = (node.get("description") or "")[:512] or None
                score = relevance_score(node["nameWithOwner"], desc or "", topics)
                is_new = fn.lower() not in known
                if is_new and score < settings.ai_filter_threshold:
                    rejected += 1
                    continue
                lic = (node.get("licenseInfo") or {}).get("spdxId")
                commit = ((node.get("defaultBranchRef") or {}).get("target") or {}).get("committedDate")
                repo_id = await conn.fetchval(
                    UPSERT_SQL,
                    node["databaseId"], node["nameWithOwner"],
                    node["owner"]["login"], node["nameWithOwner"].split("/", 1)[1],
                    f'https://github.com/{node["nameWithOwner"]}',
                    node.get("homepageUrl") or None, desc,
                    node["owner"].get("avatarUrl"),
                    (node.get("primaryLanguage") or {}).get("name"),
                    None if lic in (None, "NOASSERTION") else lic,
                    topics, node["isArchived"], node["isFork"],
                    node["stargazerCount"], node["forkCount"],
                    node["watchers"]["totalCount"], node["issues"]["totalCount"],
                    node["mentionableUsers"]["totalCount"],
                    node["createdAt"], node["pushedAt"], commit, score,
                )
                await conn.execute(
                    SNAPSHOT_SQL, repo_id,
                    node["stargazerCount"], node["forkCount"],
                    node["watchers"]["totalCount"], node["issues"]["totalCount"],
                    node["mentionableUsers"]["totalCount"],
                )
                updated += 1
                snapshots += 1
    log.info("track: updated=%s snapshots=%s rejected=%s failed=%s", updated, snapshots, rejected, failed)
    return {"updated": updated, "snapshots": snapshots, "rejected_new": rejected, "failed": failed}
