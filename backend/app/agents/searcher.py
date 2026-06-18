"""Searcher agent.

Runs a web search per sub-question (Tavily or mock fallback) and records the
collected sources on the blackboard with stable citation ids (S1, S2, ...).
On re-search rounds it targets the open gaps rather than the original
sub-questions, and de-duplicates against already-collected URLs.
"""

from __future__ import annotations

import logging

from app.agents._util import emit
from app.agents.state import ResearchState
from app.services.search import get_search_service

logger = logging.getLogger(__name__)


def searcher_node(state: ResearchState) -> dict:
    """LangGraph node: collect sources for each open question."""
    round_count = state.get("round_count", 0)
    existing = state.get("sources", [])
    existing_urls = {s["url"] for s in existing}

    # First pass searches the sub-questions; later passes target the gaps.
    if round_count == 0:
        queries = state.get("sub_questions", []) or [state["query"]]
        label = "sub-questions"
    else:
        queries = state.get("gaps", []) or state.get("sub_questions", [])
        label = "open gaps"

    emit(
        state,
        "searcher",
        "started",
        f"Searching {len(queries)} {label} (round {round_count + 1}).",
    )

    search = get_search_service()
    new_sources: list[dict] = []
    next_id = len(existing) + 1

    for q in queries:
        emit(state, "searcher", "progress", f"Searching: {q}")
        for hit in search.search(q):
            if not hit.url or hit.url in existing_urls:
                continue
            existing_urls.add(hit.url)
            new_sources.append(
                {
                    "id": f"S{next_id}",
                    "title": hit.title,
                    "url": hit.url,
                    "snippet": hit.snippet,
                    "sub_question": q,
                    "score": hit.score,
                }
            )
            next_id += 1

    emit(
        state,
        "searcher",
        "completed",
        f"Collected {len(new_sources)} new source(s) via {search.mode} search.",
        new_sources=len(new_sources),
        total_sources=len(existing) + len(new_sources),
        mode=search.mode,
    )
    # _extend reducer appends these to the accumulated source list;
    # last_new_sources lets the Critic detect a round that found nothing new.
    return {"sources": new_sources, "last_new_sources": len(new_sources)}
