import json
from typing import Any

# Cột dùng chung cho mọi màn hình dạng card/list
REPO_CARD_SQL = """
  r.full_name, r.owner, r.name, r.url, r.homepage, r.description, r.logo_url,
  r.language, r.license_spdx, r.topics, r.stars, r.forks, r.watchers, r.open_issues,
  r.contributors, r.star_growth_7d, r.star_growth_30d, r.hot_score, r.trending_flag,
  r.repo_created_at, r.last_commit_at, r.first_seen_at,
  coalesce(cat.cats, '[]') AS categories
"""

# LATERAL join gom categories thành JSON — mọi truy vấn list dùng chung
CATEGORY_LATERAL = """
  LEFT JOIN LATERAL (
    SELECT json_agg(json_build_object('slug', c.slug, 'name', c.name)) AS cats
    FROM repo_categories rc JOIN categories c ON c.id = rc.category_id
    WHERE rc.repo_id = r.id
  ) cat ON TRUE
"""


def repo_card(row: Any) -> dict:
    d = dict(row)
    if isinstance(d.get("categories"), str):
        d["categories"] = json.loads(d["categories"])
    d["license"] = d.pop("license_spdx", None)
    d.pop("search_vector", None)
    return d
