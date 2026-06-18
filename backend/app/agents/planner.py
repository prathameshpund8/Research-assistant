"""Planner agent.

Decomposes the user's query into 3–6 focused sub-questions plus a short
research plan. This is the first node in the graph.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
PLANNER_SYSTEM_PROMPT = """You are the Planner in a multi-agent research system.
Given a research topic, decompose it into 3 to 6 specific, non-overlapping
sub-questions that together fully cover the topic. Also write a one-paragraph
research plan describing the angle and what a good answer needs.

Return STRICT JSON only, with this shape:
{
  "plan": "<one paragraph>",
  "sub_questions": ["<q1>", "<q2>", "..."]
}
Do not include any text outside the JSON."""

PLANNER_USER_TEMPLATE = "Research topic:\n{query}"
# ===========================================================================

MIN_SUBQS, MAX_SUBQS = 3, 6


def planner_node(state: ResearchState) -> dict:
    """LangGraph node: produce sub_questions + plan."""
    query = state["query"]
    emit(state, "planner", "started", f"Planning research for: {query!r}")

    try:
        llm = get_llm(temperature=0.2)
        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=PLANNER_USER_TEMPLATE.format(query=query)),
        ]
        raw = llm.invoke(messages).content
        parsed = parse_json(raw, fallback={})
    except Exception as exc:  # LLM unavailable -> deterministic degraded plan
        logger.exception("Planner LLM call failed; using degraded plan.")
        emit(state, "planner", "progress", f"LLM unavailable ({exc}); using a basic plan.")
        parsed = {}

    sub_questions = parsed.get("sub_questions") or _fallback_subquestions(query)
    sub_questions = [q.strip() for q in sub_questions if isinstance(q, str) and q.strip()]
    sub_questions = sub_questions[:MAX_SUBQS]
    if len(sub_questions) < MIN_SUBQS:
        sub_questions = _fallback_subquestions(query)

    plan = parsed.get("plan") or f"Investigate '{query}' across {len(sub_questions)} angles."

    emit(
        state,
        "planner",
        "completed",
        f"Decomposed into {len(sub_questions)} sub-questions.",
        sub_questions=sub_questions,
        plan=plan,
    )
    return {"sub_questions": sub_questions, "plan": plan}


def _fallback_subquestions(query: str) -> list[str]:
    """Heuristic decomposition when the LLM can't be reached."""
    return [
        f"What is {query} and why does it matter?",
        f"What are the key facts, data, or components of {query}?",
        f"What are the main challenges, debates, or risks around {query}?",
        f"What are recent developments or the current state of {query}?",
    ]
