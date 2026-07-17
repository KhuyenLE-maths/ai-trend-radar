"""Tính growth + Hot Score bằng SQL set-based (mục 9) — 100k repo chạy trong vài giây.

Ghi chú: thành phần ACT (commit/PR activity) sẽ bổ sung ở Phase 2 khi crawl
thêm metrics hoạt động; trọng số hiện tại đã phân bổ lại như bên dưới.
"""
import logging

import asyncpg

log = logging.getLogger("pipeline.rank")

GROWTH_SQL = """
WITH s7 AS (
  SELECT DISTINCT ON (repo_id) repo_id, stars
  FROM repo_snapshots WHERE snapshot_date <= CURRENT_DATE - 7
  ORDER BY repo_id, snapshot_date DESC
), s30 AS (
  SELECT DISTINCT ON (repo_id) repo_id, stars
  FROM repo_snapshots WHERE snapshot_date <= CURRENT_DATE - 30
  ORDER BY repo_id, snapshot_date DESC
), fs AS (
  SELECT DISTINCT ON (repo_id) repo_id, stars
  FROM repo_snapshots ORDER BY repo_id, snapshot_date ASC
)
UPDATE repositories r SET
  star_growth_7d  = GREATEST(r.stars - COALESCE(s7.stars,  fs.stars, r.stars), 0),
  star_growth_30d = GREATEST(r.stars - COALESCE(s30.stars, fs.stars, r.stars), 0)
FROM fs
LEFT JOIN s7  ON s7.repo_id  = fs.repo_id
LEFT JOIN s30 ON s30.repo_id = fs.repo_id
WHERE fs.repo_id = r.id
"""

# Trọng số: V7=0.35, V30=0.15, ACC=0.10, SZ=0.15, CM=0.15, TR=0.10 (tổng = 1.0)
HOT_SCORE_SQL = """
WITH mention AS (
  SELECT repo_id, sum(score) AS pts
  FROM repo_mentions WHERE mentioned_at > now() - INTERVAL '7 days'
  GROUP BY repo_id
), scored AS (
  SELECT r.id,
    percent_rank() OVER (ORDER BY r.star_growth_7d)  AS v7,
    percent_rank() OVER (ORDER BY r.star_growth_30d) AS v30,
    percent_rank() OVER (ORDER BY log(10.0, (r.stars + 1)::numeric)) AS sz,
    percent_rank() OVER (ORDER BY
        log(10.0, (r.forks + 1)::numeric)
      + log(10.0, (COALESCE(r.contributors, 0) + 1)::numeric)
      + log(10.0, (COALESCE(m.pts, 0) + 1)::numeric)) AS cm,
    (CASE WHEN r.trending_flag THEN 1.0 ELSE 0.0 END) AS tr,
    (CASE WHEN r.last_commit_at IS NULL THEN 0.8
          WHEN r.last_commit_at < now() - INTERVAL '180 days' THEN 0.5
          WHEN r.last_commit_at < now() - INTERVAL '90 days'  THEN 0.8
          ELSE 1.0 END) AS mp,
    (CASE WHEN r.repo_created_at > now() - INTERVAL '14 days'
               AND COALESCE(r.contributors, 0) < 3 THEN 0.85 ELSE 1.0 END) AS fp
  FROM repositories r
  LEFT JOIN mention m ON m.repo_id = r.id
  WHERE NOT r.is_archived
)
UPDATE repositories r SET hot_score = ROUND((
    100.0 * ( 0.35 * s.v7
            + 0.15 * s.v30
            + 0.10 * GREATEST(s.v7 - s.v30, 0)
            + 0.15 * s.sz
            + 0.15 * s.cm
            + 0.10 * s.tr )
    * s.mp * s.fp
  )::numeric, 1)
FROM scored s WHERE s.id = r.id
"""


async def rank(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        g = await conn.execute(GROWTH_SQL)
        h = await conn.execute(HOT_SCORE_SQL)
    log.info("rank: growth=%s hot=%s", g, h)
    return {"growth_updated": g, "hot_updated": h}
