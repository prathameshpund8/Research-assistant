"""The shared LangGraph "blackboard" state.

Every node receives this :class:`ResearchState` TypedDict, reads what it needs,
and returns a partial dict of updates that LangGraph merges in. Keeping the
contract in one place is what guarantees citation integrity: sources and facts
carry stable ids that the Writer maps claims onto.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, TypedDict


def _take_last(_old: Any, new: Any) -> Any:
    """Reducer: later writers overwrite earlier values for scalar fields."""
    return new


def _extend(old: list, new: list) -> list:
    """Reducer: append-only accumulation for list fields across rounds/nodes."""
    return (old or []) + (new or [])


# Type aliases for the structured dicts carried in lists. We use plain dicts in
# the graph state (LangGraph serialises them) and validate at the API boundary
# with the Pydantic models in app/models/schemas.py.
SourceDict = dict[str, Any]
FactDict = dict[str, Any]
EventEmitter = Callable[[str, str, str, dict[str, Any]], None]


class ResearchState(TypedDict, total=False):
    """Blackboard passed between all agents."""

    # --- inputs -----------------------------------------------------------
    query: str

    # --- planner ----------------------------------------------------------
    sub_questions: list[str]
    plan: str

    # --- searcher (accumulates across re-search rounds) -------------------
    sources: Annotated[list[SourceDict], _extend]
    # How many *new* sources the most recent search round added (loop guard).
    last_new_sources: int

    # --- summarizer -------------------------------------------------------
    facts: Annotated[list[FactDict], _extend]

    # --- critic -----------------------------------------------------------
    gaps: list[str]
    contradictions: list[str]
    round_count: int
    should_research_more: bool

    # --- writer -----------------------------------------------------------
    final_report: str

    # --- paper pipeline (IEEE paper generator) ----------------------------
    # Inputs / outline
    details: str
    authors: list[dict]
    paper_title: str
    keywords: list[str]
    section_plan: list[dict]  # [{heading, guidance}]
    # Built artefacts
    abstract: str
    sections: list[dict]  # [{heading, body}]
    references: list[dict]  # [{number, source_id, text, url}]
    originality: dict
    verification: dict
    paper_markdown: str

    # --- orchestration ----------------------------------------------------
    # Callback used by nodes to emit SSE progress events. Not serialised into
    # the final result; supplied at invocation time.
    emit: EventEmitter
    error: str


def new_state(query: str, emit: EventEmitter | None = None) -> ResearchState:
    """Construct an initial state for a research run."""
    return ResearchState(
        query=query,
        sub_questions=[],
        plan="",
        sources=[],
        last_new_sources=0,
        facts=[],
        gaps=[],
        contradictions=[],
        round_count=0,
        should_research_more=False,
        final_report="",
        emit=emit or (lambda *_args, **_kw: None),
        error="",
    )
