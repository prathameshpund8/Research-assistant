"""Tables agent — generates a grounded comparison/summary table.

Produces one IEEE table (caption, columns, rows) synthesised from the collected
facts (e.g. comparing approaches, methods, or aspects of the topic). Falls back
to a simple two-column "Aspect / Finding" table if the LLM is unavailable.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.services.llm import get_fast_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
TABLE_SYSTEM_PROMPT = """You design ONE summary table for an IEEE paper from the
given facts. Choose a useful comparison (e.g. approaches, methods, applications,
or challenges vs. solutions). 3-5 columns, 3-6 rows. Keep cells short (<= 12
words). Use ONLY information supported by the facts.

Return STRICT JSON only:
{
  "caption": "<concise table caption>",
  "columns": ["Col1", "Col2", "..."],
  "rows": [["...", "..."], ["...", "..."]]
}
No text outside the JSON."""

TABLE_USER_TEMPLATE = "Topic: {topic}\n\nFacts:\n{facts}"
# ===========================================================================


def tables_node(state: ResearchState) -> dict:
    topic = state.get("paper_title", state["query"])
    facts = state.get("facts", [])
    facts_block = "\n".join(f"- {f['text']}" for f in facts[:30]) or "(none)"

    emit(state, "writer", "started", "Generating a summary table.")

    table: dict | None = None
    try:
        llm = get_fast_llm(temperature=0.3)
        msgs = [
            SystemMessage(content=TABLE_SYSTEM_PROMPT),
            HumanMessage(content=TABLE_USER_TEMPLATE.format(topic=topic, facts=facts_block)),
        ]
        parsed = parse_json(llm.invoke(msgs).content, fallback={})
        cols = [str(c) for c in parsed.get("columns", []) if str(c).strip()]
        rows = [
            [str(c) for c in row]
            for row in parsed.get("rows", [])
            if isinstance(row, list) and row
        ]
        # Normalise ragged rows to the column count.
        if cols and rows:
            rows = [(r + [""] * len(cols))[: len(cols)] for r in rows]
            table = {
                "number": 1,
                "caption": (parsed.get("caption") or f"Summary of {topic}").strip(),
                "columns": cols,
                "rows": rows[:6],
            }
    except Exception as exc:
        logger.warning("Tables agent failed (%s); using fallback table.", exc)

    if table is None:
        table = _fallback_table(topic, facts)

    emit(
        state,
        "writer",
        "completed",
        f"Table ready: '{table['caption']}' ({len(table['rows'])} rows).",
    )
    return {"tables": [table]}


def _fallback_table(topic: str, facts: list[dict]) -> dict:
    rows = [[f"Aspect {i + 1}", f["text"][:80]] for i, f in enumerate(facts[:5])]
    return {
        "number": 1,
        "caption": f"Key Findings on {topic}",
        "columns": ["Aspect", "Finding"],
        "rows": rows or [["—", "No data"]],
    }
