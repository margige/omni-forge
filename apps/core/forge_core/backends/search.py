"""Web search: SearXNG when configured, DuckDuckGo keyless, Bing last resort."""

from __future__ import annotations

import asyncio

import httpx

from ..config import CoreConfig
from .base import Backend


class SearXNGSearchBackend(Backend):
    name = "searxng"
    capability = "search"

    def __init__(self, config: CoreConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=15, follow_redirects=True)

    def available(self) -> bool:
        return self.config.searxng_configured

    async def run(self, *, query: str, limit: int = 8, **_: object) -> dict:
        response = await self._client.get(
            f"{self.config.searxng_base_url}/search",
            params={"q": query, "format": "json"},
        )
        response.raise_for_status()
        results = response.json().get("results", [])[:limit]
        return {
            "backend": self.name,
            "query": query,
            "results": [
                {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
                for r in results
            ],
        }


class DuckDuckGoSearchBackend(Backend):
    name = "duckduckgo"
    capability = "search"
    _ENDPOINTS = (
        "https://html.duckduckgo.com/html/",
        "https://lite.duckduckgo.com/lite/",
        "https://duckduckgo.com/html/",
    )

    def __init__(self, config: CoreConfig):
        self._client = httpx.AsyncClient(
            timeout=15, follow_redirects=True, headers={"user-agent": "Mozilla/5.0"}
        )

    async def run(self, *, query: str, limit: int = 8, **_: object) -> dict:
        """Try every endpoint concurrently, first non-empty reply wins.

        Three serial timeouts can total 45s on a blocked network; parallelising
        bounds the worst case at 15s while still covering every mirror.
        """
        try:
            results: list[dict] = await asyncio.wait_for(self._gather(query, limit), timeout=15)
        except TimeoutError:
            results = []
        return {"backend": self.name, "query": query, "results": results}

    async def _gather(self, query: str, limit: int) -> list[dict]:
        async def one(endpoint: str) -> list[dict]:
            try:
                response = await self._client.get(endpoint, params={"q": query})
                response.raise_for_status()
                return self._parse(response.text, limit)
            except httpx.HTTPError:
                return []

        for results in await asyncio.gather(*(one(ep) for ep in self._ENDPOINTS)):
            if results:
                return results
        return []

    def _parse(self, html: str, limit: int) -> list[dict]:
        import re
        from urllib.parse import parse_qs, unquote, urlparse

        results: list[dict] = []
        for block in re.split(r'class="result[ ">]', html):
            if not block.strip():
                continue
            title = re.search(r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
            snippet = re.search(r'result__snippet"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
            if not title:
                continue
            clean = lambda s: re.sub(r"<[^>]+>", "", s).strip()
            t = clean(title.group(2))
            if not t:
                continue
            href = title.group(1)
            parsed = urlparse(href)
            query = parse_qs(parsed.query)
            url = unquote(query["uddg"][0]) if "uddg" in query else href
            results.append(
                {
                    "title": t,
                    "url": url,
                    "snippet": clean(snippet.group(1)) if snippet else "",
                }
            )
            if len(results) >= limit:
                break
        return results


class BingSearchBackend(Backend):
    name = "bing"
    capability = "search"

    def __init__(self, config: CoreConfig):
        self._client = httpx.AsyncClient(
            timeout=20, follow_redirects=True, headers={"user-agent": "Mozilla/5.0"}
        )

    async def run(self, *, query: str, limit: int = 8, **_: object) -> dict:
        response = await self._client.get("https://www.bing.com/search", params={"q": query})
        response.raise_for_status()
        results = self._parse(response.text, limit)
        return {"backend": self.name, "query": query, "results": results}

    def _parse(self, html: str, limit: int) -> list[dict]:
        import re

        results: list[dict] = []
        for block in re.split(r'<li class="b_algo"', html):
            if not block.strip():
                continue
            title = re.search(r"<h2[^>]*>\s*<a\s+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, flags=re.DOTALL)
            snippet = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.DOTALL)
            if not title:
                continue
            clean = lambda s: re.sub(r"<[^>]+>", "", s).strip()
            t = clean(title.group(2))
            if not t:
                continue
            results.append(
                {
                    "title": t,
                    "url": title.group(1),
                    "snippet": clean(snippet.group(1)) if snippet else "",
                }
            )
            if len(results) >= limit:
                break
        return results
