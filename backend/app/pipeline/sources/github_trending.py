"""GitHub Trending không có API chính thức → scrape HTML nhẹ nhàng, fail-soft.

Đây là TÍN HIỆU BỔ SUNG (trọng số 0.10 trong Hot Score) — scrape fail thì
pipeline vẫn tiếp tục bình thường (rủi ro #2 trong tài liệu thiết kế).
"""
import logging

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("pipeline.trending")

LANGS = ["", "python", "typescript", "rust", "jupyter-notebook", "go"]


async def fetch_trending() -> set[str]:
    names: set[str] = set()
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": "ai-trend-radar/1.0 (internal tool)"}, follow_redirects=True
    ) as client:
        for lang in LANGS:
            url = f"https://github.com/trending/{lang}?since=daily" if lang else "https://github.com/trending?since=daily"
            try:
                r = await client.get(url)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select("article.Box-row h2 a"):
                    href = (a.get("href") or "").strip("/")
                    if href.count("/") == 1:
                        names.add(href)
            except Exception as e:
                log.warning("trending scrape fail (%s): %s", lang or "all", e)
    log.info("trending: %s repos", len(names))
    return names


async def apply_trending_flags(pool, names: set[str]) -> int:
    """Reset toàn bộ cờ rồi bật cho các repo trong danh sách hôm nay."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE repositories SET trending_flag = FALSE WHERE trending_flag")
        if not names:
            return 0
        res = await conn.execute(
            "UPDATE repositories SET trending_flag = TRUE WHERE lower(full_name) = ANY($1)",
            [n.lower() for n in names],
        )
    return int(res.split()[-1])
