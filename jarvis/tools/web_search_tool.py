"""
jarvis/tools/web_search_tool.py
-------------------------------
Free web-search aggregation for the Research Agent.

Primary source: DuckDuckGo HTML endpoint (no API key required).
Fallback: a lightweight Bing HTML scrape. All results are title/link/snippet
tuples so the LLM can synthesize answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchTool:
    """Search the web using free, key-less endpoints."""

    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Run a web search and return ranked results."""
        results = self._duckduckgo_html(query, max_results)
        if not results:
            results = self._bing_html(query, max_results)
        return results[:max_results]

    # ------------------------------------------------------------------ #
    # DuckDuckGo HTML (no key, no JS)
    # ------------------------------------------------------------------ #
    def _duckduckgo_html(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": self.UA},
                timeout=15,
            )
            resp.raise_for_status()
            return self._parse_ddg(resp.text, max_results)
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _parse_ddg(html: str, max_results: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        # DDG result blocks are wrapped in .result with .result__a / .result__snippet
        # We avoid a hard HTML dependency by using lightweight regexes.
        blocks = re.findall(
            r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>',
            html,
            flags=re.DOTALL,
        )
        snippets = re.findall(
            r'<a class="result__snippet".*?>(.*?)</a>',
            html,
            flags=re.DOTALL,
        )
        for idx, (url, title) in enumerate(blocks):
            if idx >= max_results:
                break
            clean_title = re.sub(r"<.*?>", "", title).strip()
            clean_url = re.sub(r"&amp;", "&", url)
            snippet = ""
            if idx < len(snippets):
                snippet = re.sub(r"<.*?>", "", snippets[idx]).strip()
            if clean_title and clean_url:
                results.append(SearchResult(title=clean_title, url=clean_url, snippet=snippet))
        return results

    # ------------------------------------------------------------------ #
    # Bing HTML fallback
    # ------------------------------------------------------------------ #
    def _bing_html(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            resp = requests.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers={"User-Agent": self.UA},
                timeout=15,
            )
            resp.raise_for_status()
            return self._parse_bing(resp.text, max_results)
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _parse_bing(html: str, max_results: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        for m in re.finditer(
            r'<li class="b_algo".*?<h2.*?<a href="([^"]+)">(.*?)</a>.*?</h2>.*?'
            r'(?:<p>(.*?)</p>)?',
            html,
            flags=re.DOTALL,
        ):
            if len(results) >= max_results:
                break
            url, title, snippet = m.group(1), m.group(2), m.group(3) or ""
            clean_title = re.sub(r"<.*?>", "", title).strip()
            clean_snippet = re.sub(r"<.*?>", "", snippet).strip()
            if clean_title and url:
                results.append(SearchResult(title=clean_title, url=url, snippet=clean_snippet))
        return results

    def format_for_llm(self, results: list[SearchResult]) -> str:
        if not results:
            return "No web results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}")
        return "\n".join(lines)


def search_web(query: str, max_results: int = 5) -> str:
    """Convenience function returning an LLM-ready string."""
    tool = WebSearchTool()
    results = tool.search(query, max_results=max_results)
    return tool.format_for_llm(results)
