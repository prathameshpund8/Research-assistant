"""Critic agent.

Cross-checks the extracted facts against the sub-questions, flags coverage
gaps and contradictions, and decides whether another search round is warranted.

Loop termination rules (all enforced here):
  1. Hard cap of ``settings.max_research_rounds`` re-search rounds.
  2. Stop if the most recent search round found no new sources.
  3. Stop when the Critic reports no remaining gaps.
The actual routing (back to Searcher vs. on to Writer) is decided by
``should_continue`` in graph.py based on the flags this node sets.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.config import get_settings
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
CRITIC_SYSTEM_PROMPT = """You are the Critic in a research system. You verify
coverage and consistency. Given the sub-questions and the facts gathered so far
(each tagged with a source id), assess:
- Which sub-questions are NOT yet adequately answered (gaps).
- Any contradictions between facts (cite the conflicting source ids).

Return STRICT JSON only:
{
  "gaps": ["<missing aspect / unanswered sub-question>", "..."],
  "contradictions": ["<short description incl. source ids>", "..."]
}
Return empty lists if coverage is solid and consistent. No text outside JSON."""

CRITIC_USER_TEMPLATE = "Sub-questions:\n{sub_questions}\n\nFacts gathered:\n{facts}"
# ===========================================================================


def critic_node(state: ResearchState) -> dict:
    """LangGraph node: assess coverage, set gaps + should_research_more."""
    settings = get_settings()
    round_count = state.get("round_count", 0)
    sub_questions = state.get("sub_questions", [])
    facts = state.get("facts", [])

    emit(state, "critic", "started", "Cross-checking facts and looking for gaps.")

    gaps: list[str] = []
    contradictions: list[str] = []
    try:
        llm = get_llm(temperature=0.1)
        facts_text = "\n".join(f"- ({f['source_id']}) {f['text']}" for f in facts) or "(none)"
        sub_text = "\n".join(f"- {q}" for q in sub_questions) or "(none)"
        messages = [
            SystemMessage(content=CRITIC_SYSTEM_PROMPT),
            HumanMessage(
                content=CRITIC_USER_TEMPLATE.format(sub_questions=sub_text, facts=facts_text)
            ),
        ]
        parsed = parse_json(llm.invoke(messages).content, fallback={})
        gaps = [g for g in parsed.get("gaps", []) if isinstance(g, str) and g.strip()]
        contradictions = [
            c for c in parsed.get("contradictions", []) if isinstance(c, str) and c.strip()
        ]
    except Exception as exc:
        logger.warning("Critic LLM unavailable (%s); accepting current coverage.", exc)
        emit(state, "critic", "progress", f"LLM unavailable ({exc}); accepting coverage.")
        gaps = [] if facts else list(sub_questions)

    # --- decide whether to loop ------------------------------------------
    next_round = round_count + 1
    last_new = state.get("last_new_sources", 0)
    reasons: list[str] = []

    should_more = bool(gaps)
    if should_more and next_round > settings.max_research_rounds:
        should_more = False
        reasons.append(f"hit max rounds ({settings.max_research_rounds})")
    if should_more and last_new == 0 and round_count > 0:
        should_more = False
        reasons.append("previous round found no new sources")

    decision = "re-search" if should_more else "proceed to writer"
    detail = f" ({'; '.join(reasons)})" if reasons else ""
    emit(
        state,
        "critic",
        "completed",
        f"{len(gaps)} gap(s), {len(contradictions)} contradiction(s) → {decision}{detail}.",
        gaps=gaps,
        contradictions=contradictions,
        decision=decision,
        round_count=next_round,
    )

    return {
        "gaps": gaps,
        "contradictions": contradictions,
        "round_count": next_round,
        "should_research_more": should_more,
    }
