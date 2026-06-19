"""Summarizer agent.

Hierarchical summarization: each source is summarized *individually* into a
handful of atomic facts before any final synthesis. Every fact keeps its
``source_id`` so the Writer can cite it. Only newly-collected sources (those
without facts yet) are processed, which also keeps us within context limits
across re-search rounds.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.services.llm import get_fast_llm as get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
SUMMARIZER_SYSTEM_PROMPT = """You are the Summarizer in a research system.
Extract 1 to 4 concise, atomic, factual claims from the provided source text.
Rules:
- Only state facts actually supported by the text. Do not add outside knowledge.
- Each fact must be a single self-contained sentence.
- If the text is empty or contains no usable facts, return an empty list.

Return STRICT JSON only:
{ "facts": ["<fact 1>", "<fact 2>"] }
No text outside the JSON."""

SUMMARIZER_USER_TEMPLATE = (
    "Sub-question: {sub_question}\n"
    "Source title: {title}\n"
    "Source text:\n{snippet}"
)
# ===========================================================================


def summarizer_node(state: ResearchState) -> dict:
    """LangGraph node: turn new sources into attributed facts."""
    sources = state.get("sources", [])
    already = {f["source_id"] for f in state.get("facts", [])}
    pending = [s for s in sources if s["id"] not in already]

    emit(
        state,
        "summarizer",
        "started",
        f"Extracting facts from {len(pending)} new source(s).",
    )

    new_facts: list[dict] = []
    try:
        llm = get_llm(temperature=0.1)
        llm_ok = True
    except Exception as exc:
        logger.warning("Summarizer LLM unavailable (%s); using snippet fallback.", exc)
        emit(state, "summarizer", "progress", f"LLM unavailable ({exc}); summarising heuristically.")
        llm = None
        llm_ok = False

    for src in pending:
        if llm_ok:
            try:
                messages = [
                    SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
                    HumanMessage(
                        content=SUMMARIZER_USER_TEMPLATE.format(
                            sub_question=src.get("sub_question", ""),
                            title=src.get("title", ""),
                            snippet=(src.get("snippet") or "")[:2000],
                        )
                    ),
                ]
                parsed = parse_json(llm.invoke(messages).content, fallback={})
                facts = parsed.get("facts", [])
            except Exception:
                logger.exception("Summarizer failed on %s; falling back to snippet.", src["id"])
                facts = _snippet_fallback(src)
        else:
            facts = _snippet_fallback(src)

        for fact in facts:
            if isinstance(fact, str) and fact.strip():
                new_facts.append({"text": fact.strip(), "source_id": src["id"]})

        emit(state, "summarizer", "progress", f"{src['id']}: extracted {len(facts)} fact(s).")

    emit(
        state,
        "summarizer",
        "completed",
        f"Extracted {len(new_facts)} attributed fact(s).",
        new_facts=len(new_facts),
    )
    return {"facts": new_facts}


def _snippet_fallback(src: dict) -> list[str]:
    """Use the raw snippet as a single fact if the LLM is unavailable."""
    snippet = (src.get("snippet") or "").strip()
    return [snippet[:280]] if snippet else []
