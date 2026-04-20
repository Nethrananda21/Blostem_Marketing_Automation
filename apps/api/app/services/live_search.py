from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from apps.api.app.config import Settings


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
DDG_LINK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
DDG_SNIPPET_RE = re.compile(
    r'<(?:a|div)[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class LiveCompanyResearchFinding:
    title: str
    summary: str
    source_url: str
    provider: str
    query: str
    published_at: datetime | None = None


class LiveCompanyResearchTool:
    """Deterministic live-search tool used by the sidebar agent before LLM synthesis."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def live_company_research(
        self,
        *,
        company_name: str,
        prompt: str,
        limit: int | None = None,
    ) -> list[LiveCompanyResearchFinding]:
        max_results = max(1, min(limit or self.settings.live_search_max_results, 8))
        query = self._build_query(company_name, prompt)
        provider = self._provider()
        if provider == "tavily":
            try:
                return await self._search_tavily(query=query, max_results=max_results)
            except httpx.HTTPError:
                if self.settings.live_search_provider == "tavily":
                    raise
        return await self._search_duckduckgo(query=query, max_results=max_results)

    def _provider(self) -> str:
        if self.settings.live_search_provider == "tavily":
            return "tavily"
        if self.settings.live_search_provider == "duckduckgo":
            return "duckduckgo"
        return "tavily" if self.settings.tavily_api_key else "duckduckgo"

    def _build_query(self, company_name: str, prompt: str) -> str:
        prompt_terms = SPACE_RE.sub(" ", prompt).strip()
        if company_name.lower() not in prompt_terms.lower():
            prompt_terms = f'"{company_name}" {prompt_terms}'
        if "india" not in prompt_terms.lower():
            prompt_terms = f"{prompt_terms} India"
        return prompt_terms[:280]

    async def _search_tavily(
        self,
        *,
        query: str,
        max_results: int,
    ) -> list[LiveCompanyResearchFinding]:
        if not self.settings.tavily_api_key:
            return []
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.settings.tavily_api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
        payload = response.json()
        findings: list[LiveCompanyResearchFinding] = []
        for item in payload.get("results", [])[:max_results]:
            title = self._clean_text(str(item.get("title") or "Untitled source"))
            source_url = str(item.get("url") or "").strip()
            if not source_url:
                continue
            summary = self._clean_text(str(item.get("content") or title))
            published_at = self._parse_datetime(item.get("published_date"))
            findings.append(
                LiveCompanyResearchFinding(
                    title=title[:240],
                    summary=summary[:520],
                    source_url=source_url[:500],
                    provider="tavily",
                    query=query,
                    published_at=published_at,
                ),
            )
        return findings

    async def _search_duckduckgo(
        self,
        *,
        query: str,
        max_results: int,
    ) -> list[LiveCompanyResearchFinding]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 BlostemLiveResearch/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        snippets = [self._clean_text(match.group("snippet")) for match in DDG_SNIPPET_RE.finditer(response.text)]
        findings: list[LiveCompanyResearchFinding] = []
        seen_urls: set[str] = set()
        for index, match in enumerate(DDG_LINK_RE.finditer(response.text)):
            source_url = self._clean_duckduckgo_url(match.group("href"))
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            title = self._clean_text(match.group("title")) or "Untitled source"
            summary = snippets[index] if index < len(snippets) and snippets[index] else title
            findings.append(
                LiveCompanyResearchFinding(
                    title=title[:240],
                    summary=summary[:520],
                    source_url=source_url[:500],
                    provider="duckduckgo",
                    query=query,
                    published_at=None,
                ),
            )
            if len(findings) >= max_results:
                break
        return findings

    def _clean_text(self, value: str) -> str:
        return SPACE_RE.sub(" ", TAG_RE.sub(" ", html.unescape(value or ""))).strip()

    def _clean_duckduckgo_url(self, value: str) -> str:
        raw_url = html.unescape(value or "")
        parsed = urlparse(raw_url)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return unquote(query["uddg"][0])
        if raw_url.startswith("//"):
            return f"https:{raw_url}"
        return raw_url

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
