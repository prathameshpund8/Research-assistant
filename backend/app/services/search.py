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


# Hosts / URL fragments that indicate ads, trackers, or non-citable content.
_JUNK_URL_FRAGMENTS = (
    "bing.com/aclick",
    "duckduckgo.com/y.js",
    "/aclk?",
    "googleadservices",
    "doubleclick.net",
    "utm_campaign",
    "/sponsored",
)

# Low-credibility sources for an academic paper: contract-cheating / essay mills
# and assignment-writing services. Specific brands/patterns to avoid blocking
# legitimate research URLs that merely contain the word "essay".
_BLOCKED_FRAGMENTS = (
    "ukessays", "essaypro", "essayshark", "essaywriter", "myessay",
    "bestessay", "essaytyper", "edubirdie", "paperhelp", "writemypaper",
    "paperwriting", "quickassignmenthub", "assignmenthub", "assignmenthelp",
    "myassignment", "homeworkhelp", "courseworkhelp", "studymoose",
    "coursehero", "studocu", "chegg.com", "gradesfixer", "bartleby.com",
    "scribbr.com/essay",
)

# Substrings that indicate a high-credibility scholarly source (ranked first).
_SCHOLARLY_HINTS = (
    ".edu", ".gov", ".ac.", "doi.org", "arxiv.org", "ieee.org", "ieeexplore",
    "springer", "link.springer", "sciencedirect", "mdpi.com", "nature.com",
    "ncbi.nlm.nih.gov", "/pmc/", "pmc.ncbi", "frontiersin.org", "wiley.com",
    "onlinelibrary.wiley", "acm.org", "researchgate.net", "eric.ed.gov",
    "semanticscholar", "tandfonline", "sagepub", "cambridge.org", "oup.com",
    "jstor.org", "plos.org", "biomedcentral", "scopus",
)


def is_quality_url(url: str) -> bool:
    """Reject ad/tracking redirects and known low-credibility/essay-mill hosts."""
    low = url.lower()
    if not low.startswith(("http://", "https://")):
        return False
    if any(frag in low for frag in _JUNK_URL_FRAGMENTS):
        return False
    if any(frag in low for frag in _BLOCKED_FRAGMENTS):
        return False
    return True


def credibility(url: str) -> int:
    """Heuristic source credibility for ranking (higher = more scholarly)."""
    low = url.lower()
    if any(h in low for h in _SCHOLARLY_HINTS):
        return 3
    if low.split("/")[2:3] and low.split("/")[2].endswith((".org", ".edu", ".gov")):
        return 2
    return 1


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
        """Keyless real web search via DuckDuckGo (ddgs package).

        Over-fetches, drops ad/tracking redirects and essay-mill/junk hosts, then
        ranks scholarly sources first so the paper cites credible references.
        """
        from ddgs import DDGS

        candidates: list[RawResult] = []
        with DDGS() as ddgs_client:
            # Over-fetch generously so filtering + scholarly ranking has choice.
            raw = ddgs_client.text(query, max_results=max(k * 4, 12))
            for order, item in enumerate(raw):
                url = item.get("href") or item.get("url") or ""
                if not url or not is_quality_url(url):
                    continue
                # Score = credibility tier first, then original result order.
                cred = credibility(url)
                candidates.append(
                    RawResult(
                        title=item.get("title") or url,
                        url=url,
                        snippet=(item.get("body") or "")[:600],
                        score=round(cred + max(0.0, 1.0 - order * 0.05), 2),
                    )
                )

        # Prefer higher credibility, then earlier result order (encoded in score).
        candidates.sort(key=lambda r: r.score, reverse=True)
        return candidates[:k]

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
