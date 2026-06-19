"""Web search wrapper with a deterministic mock fallback.

If ``TAVILY_API_KEY`` is present we query Tavily; otherwise we return a
deterministic mock result set so the whole app remains runnable offline / in
CI without external keys. Both paths return the same normalised shape.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RawResult:
    """Provider-agnostic search hit before it becomes a citable Source."""

    title: str
    url: str
    snippet: str
    score: float = 0.0


class SearchService:
    """Web search facade with tiered providers.

    Provider preference: **Tavily** (if a key is set) → **DuckDuckGo** (keyless,
    real web results) → **mock** (offline placeholders). Each tier also degrades
    to the next at *runtime* if a call fails.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None
        self._mode = "mock"

        # Trust the OS/corporate CA before any provider makes HTTPS calls.
        from app.tls import configure_tls

        configure_tls()

        if self._settings.has_tavily:
            try:
                from tavily import TavilyClient  # imported lazily

                self._client = TavilyClient(api_key=self._settings.tavily_api_key)
                self._mode = "tavily"
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Tavily init failed (%s); trying keyless search.", exc)

        # No Tavily key? Use keyless DuckDuckGo if the package is available.
        if self._mode == "mock":
            try:
                import ddgs  # noqa: F401

                self._mode = "duckduckgo"
            except Exception:
                logger.info("ddgs not installed; using mock search.")

        logger.info("SearchService initialised in '%s' mode.", self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def search(self, query: str, max_results: Optional[int] = None) -> list[RawResult]:
        """Return up to ``max_results`` hits for ``query`` (degrading on failure)."""
        k = max_results or self._settings.search_results_per_query

        if self._mode == "tavily" and self._client is not None:
            try:
                return self._search_tavily(query, k)
            except Exception as exc:  # network / quota errors -> degrade
                logger.warning("Tavily search failed (%s); trying DuckDuckGo.", exc)

        if self._mode in ("tavily", "duckduckgo"):
            try:
                results = self._search_duckduckgo(query, k)
                if results:
                    return results
                logger.warning("DuckDuckGo returned no results for %r; using mock.", query)
            except Exception as exc:
                logger.warning("DuckDuckGo search failed (%s); using mock results.", exc)

        return self._search_mock(query, k)

    # -- providers ---------------------------------------------------------
    def _search_tavily(self, query: str, k: int) -> list[RawResult]:
        resp = self._client.search(
            query=query,
            max_results=k,
            search_depth="advanced",
            include_answer=False,
        )
        results: list[RawResult] = []
        for item in resp.get("results", []):
            results.append(
                RawResult(
                    title=item.get("title") or item.get("url", "Untitled"),
                    url=item.get("url", ""),
                    snippet=(item.get("content") or "")[:600],
                    score=float(item.get("score", 0.0)),
                )
            )
        return results

    def _search_duckduckgo(self, query: str, k: int) -> list[RawResult]:
        """Keyless real web search via DuckDuckGo (ddgs package)."""
        from ddgs import DDGS

        results: list[RawResult] = []
        with DDGS() as ddgs_client:
            for rank, item in enumerate(ddgs_client.text(query, max_results=k)):
                url = item.get("href") or item.get("url") or ""
                if not url:
                    continue
                results.append(
                    RawResult(
                        title=item.get("title") or url,
                        url=url,
                        snippet=(item.get("body") or "")[:600],
                        # No provider score; approximate by result ordering.
                        score=round(max(0.0, 1.0 - rank * 0.1), 2),
                    )
                )
        return results

    def _search_mock(self, query: str, k: int) -> list[RawResult]:
        """Deterministic, clearly-labelled placeholder results.

        URLs point at example.com so they are obviously non-authoritative; the
        Writer/Critic still treat them as real collected sources for the
        purpose of citation-integrity wiring.
        """
        digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:8]
        results: list[RawResult] = []
        for i in range(1, k + 1):
            results.append(
                RawResult(
                    title=f"[MOCK] {query} — reference {i}",
                    url=f"https://example.com/mock/{digest}/{i}",
                    snippet=(
                        f"Mock source {i} for the query '{query}'. This placeholder "
                        "text stands in for a real web snippet so the research "
                        "pipeline can run without a Tavily API key. Configure "
                        "TAVILY_API_KEY to fetch live results."
                    ),
                    score=round(1.0 - i * 0.1, 2),
                )
            )
        return results

    def health(self) -> dict[str, object]:
        return {
            "mode": self._mode,  # tavily | duckduckgo | mock
            "tavily_configured": self._settings.has_tavily,
            "live": self._mode != "mock",
        }


_search_singleton: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Return a process-wide SearchService singleton."""
    global _search_singleton
    if _search_singleton is None:
        _search_singleton = SearchService()
    return _search_singleton
