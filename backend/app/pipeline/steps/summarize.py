"""AI Summary (mục 11) — tuỳ chọn, chỉ chạy khi có GEMINI_API_KEY.

Chọn lọc để kiểm soát chi phí: chỉ Top-N repo hot chưa có summary cho README
hiện tại. Cache vĩnh viễn theo (repo_id, readme_hash).
"""
import asyncio
import hashlib
import json
import logging
import re

import asyncpg
import httpx

from app.core.config import settings
from app.pipeline.raw_archive import record_raw
from app.pipeline.sources.github_client import fetch_readme_raw

log = logging.getLogger("pipeline.summarize")

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
RATE_LIMIT_WAIT_SECONDS = 60


class _GeminiStop(Exception):
    """Key hỏng, hết hạn mức hoặc model quá tải: gọi tiếp cũng vô ích."""

PROMPT = """Bạn là kỹ sư AI thẩm định công cụ cho đội ngũ nội bộ. Dựa DUY NHẤT vào metadata và README dưới đây, hãy tóm tắt repository. Không suy diễn thông tin không có trong tài liệu; mục nào không đủ căn cứ thì để chuỗi rỗng hoặc mảng rỗng.

Repository: {full_name}
Description: {description}
Topics: {topics}
Stars: {stars} | Language: {language} | License: {license}
Danh sách repo cùng loại (chỉ được chọn "alternatives" từ danh sách này): {candidates}

README:
---
{readme}
---

Trả về DUY NHẤT một JSON object đúng schema sau (viết tiếng Việt):
{{
  "tldr": "1-2 câu",
  "purpose": "giải quyết bài toán gì",
  "when_to_use": ["..."],
  "when_not_to_use": ["..."],
  "target_users": ["..."],
  "difficulty": "beginner|intermediate|advanced",
  "maturity": "experimental|emerging|production-ready|mature",
  "key_features": ["..."],
  "pros": ["..."],
  "cons": ["..."],
  "alternatives": [{{"repo": "owner/name", "note": "khác gì"}}],
  "related_tech": ["..."],
  "architecture_notes": "",
  "confidence": 0.0
}}"""

SELECT_CANDIDATES_SQL = """
SELECT r.id, r.full_name, r.description, r.topics, r.stars, r.language, r.license_spdx
FROM repositories r
WHERE NOT r.is_archived AND r.hot_score > 0
ORDER BY r.hot_score DESC
LIMIT 200
"""


def _strip_readme(text: str) -> str:
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", text)  # badge links
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)               # images
    text = re.sub(r"<[^>]+>", " ", text)                            # html tags
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:20000]


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(json)?\s*|\s*```$", "", raw, flags=re.S)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


async def _post_gemini(client: httpx.AsyncClient, prompt: str, record: dict) -> httpx.Response:
    # Key đi qua header, không để trên URL vì URL bị ghi vào log
    r = await client.post(
        f"{GEMINI_API}/models/{settings.summary_model}:generateContent",
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # Token suy luận của model cũng tính vào hạn mức này
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 8000},
        },
    )
    record_raw("gemini", record, r.status_code, r.text)
    return r


async def _generate(client: httpx.AsyncClient, prompt: str, record: dict) -> str:
    r = await _post_gemini(client, prompt, record)
    if r.status_code in (429, 503):  # hết hạn mức theo phút/model quá tải: chờ rồi thử lại một lần
        await asyncio.sleep(RATE_LIMIT_WAIT_SECONDS)
        r = await _post_gemini(client, prompt, record)
    if r.status_code in (401, 403, 429, 503) or (r.status_code == 400 and "API_KEY_INVALID" in r.text):
        raise _GeminiStop(f"Gemini trả {r.status_code}")
    r.raise_for_status()
    # Prompt bị chặn thì không có candidates
    parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


async def summarize(pool: asyncpg.Pool) -> dict:
    if not settings.gemini_api_key:
        log.info("summarize: bỏ qua (chưa cấu hình GEMINI_API_KEY)")
        return {"skipped": True}

    done = failed = 0

    async with httpx.AsyncClient(timeout=120) as client, pool.acquire() as conn:
        candidates = await conn.fetch(SELECT_CANDIDATES_SQL)
        for repo in candidates:
            if done >= settings.summary_daily_limit:
                break
            readme = await fetch_readme_raw(repo["full_name"])
            if not readme:
                continue
            readme = _strip_readme(readme)
            readme_hash = hashlib.sha256(readme.encode()).hexdigest()[:32]
            exists = await conn.fetchval(
                "SELECT 1 FROM ai_summaries WHERE repo_id = $1 AND readme_hash = $2",
                repo["id"], readme_hash,
            )
            if exists:
                continue

            similar = await conn.fetch(
                """SELECT DISTINCT r2.full_name FROM repositories r2
                   JOIN repo_categories rc2 ON rc2.repo_id = r2.id
                   WHERE rc2.category_id IN (SELECT category_id FROM repo_categories WHERE repo_id = $1)
                     AND r2.id <> $1 ORDER BY r2.full_name LIMIT 15""",
                repo["id"],
            )
            prompt = PROMPT.format(
                full_name=repo["full_name"],
                description=repo["description"] or "(không có)",
                topics=", ".join(repo["topics"] or []),
                stars=repo["stars"], language=repo["language"] or "?",
                license=repo["license_spdx"] or "?",
                candidates=", ".join(s["full_name"] for s in similar) or "(không có)",
                readme=readme,
            )
            record = {"model": settings.summary_model, "repo": repo["full_name"], "prompt": prompt}
            try:
                content = _parse_json(await _generate(client, prompt, record))
                if not content or "tldr" not in content:
                    failed += 1
                    continue
                await conn.execute(
                    """INSERT INTO ai_summaries (repo_id, readme_hash, model, content)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT (repo_id, readme_hash) DO NOTHING""",
                    repo["id"], readme_hash, settings.summary_model, json.dumps(content),
                )
                done += 1
            except _GeminiStop as e:
                log.error("summarize dừng: %s", e)
                failed += 1
                break
            except Exception as e:
                log.warning("summarize %s fail: %s", repo["full_name"], e)
                record_raw("gemini", record, None, str(e))
                failed += 1

    log.info("summarize: done=%s failed=%s", done, failed)
    return {"summarized": done, "failed": failed}
