"""HTTP client dùng chung cho GitHub REST + GraphQL, có retry/backoff và rate-limit awareness."""
import asyncio
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

log = logging.getLogger("pipeline.github")

API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        h["Authorization"] = f"token {settings.github_token}"
    return h


class GitHubError(Exception):
    pass


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, max=60),
    retry=retry_if_exception_type((httpx.TransportError, GitHubError)),
)
async def rest_get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{API}{path}", params=params, headers=_headers())
        if r.status_code in (403, 429):  # rate limited
            wait = int(r.headers.get("Retry-After", 60))
            remaining = r.headers.get("X-RateLimit-Remaining")
            log.warning("GitHub rate limited (remaining=%s), sleep %ss", remaining, wait)
            await asyncio.sleep(min(wait, 120))
            raise GitHubError("rate limited")
        if r.status_code >= 500:
            raise GitHubError(f"server error {r.status_code}")
        r.raise_for_status()
        return r.json()


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, max=60),
    retry=retry_if_exception_type((httpx.TransportError, GitHubError)),
)
async def graphql(query: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{API}/graphql", json={"query": query}, headers=_headers())
        if r.status_code in (403, 429, 502):
            await asyncio.sleep(30)
            raise GitHubError(f"graphql retryable {r.status_code}")
        r.raise_for_status()
        body = r.json()
        # GraphQL trả 200 kể cả khi có lỗi từng phần — chỉ fail khi không có data
        if body.get("data") is None:
            raise GitHubError(f"graphql errors: {body.get('errors')}")
        return body["data"]


async def fetch_readme_raw(full_name: str, max_chars: int = 24000) -> str | None:
    """Lấy README dạng text thô (cho AI Summary)."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(
                f"{API}/repos/{full_name}/readme",
                headers={**_headers(), "Accept": "application/vnd.github.raw+json"},
            )
            if r.status_code != 200:
                return None
            return r.text[:max_chars]
    except httpx.HTTPError:
        return None
