"""Phân loại đa nhãn: rule-based YAML (tầng 1) — mục 10.

Tầng LLM (tầng 2) gắn qua summarize/classify khi có API key; tầng manual
(source='manual') không bao giờ bị pipeline ghi đè (ON CONFLICT DO NOTHING).
"""
import logging
import pathlib
import re

import asyncpg
import yaml

log = logging.getLogger("pipeline.categorize")

RULES_PATH = pathlib.Path(__file__).resolve().parent.parent / "rules" / "categories.yaml"


def load_rules() -> list[dict]:
    rules = yaml.safe_load(RULES_PATH.read_text())
    for r in rules:
        r["_kw"] = [re.compile(re.escape(k), re.I) for k in r.get("any_keywords", [])]
        r["_topics"] = {t.lower() for t in r.get("any_topics", [])}
        r["_known"] = {k.lower() for k in r.get("known_repos", [])}
    return rules


def match_categories(rules: list[dict], full_name: str, description: str, topics: list[str]) -> list[tuple[str, float]]:
    text = f"{full_name} {description}"
    tset = {t.lower() for t in topics}
    out = []
    for r in rules:
        score = 0.0
        if full_name.lower() in r["_known"]:
            score += 10
        score += 3 * len(tset & r["_topics"])
        score += 2 * sum(1 for rx in r["_kw"] if rx.search(text))
        if score >= r.get("threshold", 3):
            out.append((r["category"], min(score / 10.0, 1.0)))
    return out


async def categorize(pool: asyncpg.Pool, only_uncategorized: bool = False) -> dict:
    rules = load_rules()
    where = (
        "WHERE NOT is_archived AND NOT EXISTS (SELECT 1 FROM repo_categories rc WHERE rc.repo_id = r.id)"
        if only_uncategorized
        else "WHERE NOT is_archived"
    )
    labeled = fallback = 0
    async with pool.acquire() as conn:
        cat_ids = {row["slug"]: row["id"] for row in await conn.fetch("SELECT id, slug FROM categories")}
        repos = await conn.fetch(f"SELECT id, full_name, coalesce(description,'') AS description, topics FROM repositories r {where}")
        for repo in repos:
            matches = match_categories(rules, repo["full_name"], repo["description"], repo["topics"] or [])
            if not matches:
                matches = [("other-ai", 0.3)]
                fallback += 1
            for slug, conf in matches:
                if slug not in cat_ids:
                    continue
                await conn.execute(
                    """INSERT INTO repo_categories (repo_id, category_id, confidence, source)
                       VALUES ($1, $2, $3, 'rule')
                       ON CONFLICT (repo_id, category_id) DO NOTHING""",
                    repo["id"], cat_ids[slug], conf,
                )
            labeled += 1
    log.info("categorize: labeled=%s fallback_other=%s", labeled, fallback)
    return {"labeled": labeled, "fallback_other": fallback}
