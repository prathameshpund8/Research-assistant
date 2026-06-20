"""Tables agent — generates two grounded comparison/summary tables.

Synthesises two distinct IEEE tables (caption, columns, rows) from the collected
facts. Falls back to simple tables if the LLM is unavailable.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.services.llm import get_fast_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
TABLE_SYSTEM_PROMPT = """You design TWO distinct summary tables for an IEEE paper
from the given facts. Make them cover DIFFERENT angles (e.g. table 1: applications
or methods comparison; table 2: challenges vs. solutions, or a taxonomy). Each
table: 3-5 columns, 3-6 rows, cells <= 12 words. Use ONLY the given facts.

Return STRICT JSON only:
{
  "tables": [
    {"caption": "...", "columns": ["...","..."], "rows": [["...","..."]]},
    {"caption": "...", "columns": ["...","..."], "rows": [["...","..."]]}
  ]
}
No text outside the JSON."""

TABLE_USER_TEMPLATE = "Topic: {topic}\n\nFacts:\n{facts}"
# ===========================================================================

_TARGET_TABLES = 2


def tables_node(state: ResearchState) -> dict:
    topic = state.get("paper_title", state["query"])
    facts = state.get("facts", [])
    facts_block = "\n".join(f"- {f['text']}" for f in facts[:30]) or "(none)"

    emit(state, "writer", "started", "Generating summary tables.")

    tables: list[dict] = []
    try:
        llm = get_fast_llm(temperature=0.3)
        msgs = [
            SystemMessage(content=TABLE_SYSTEM_PROMPT),
            HumanMessage(content=TABLE_USER_TEMPLATE.format(topic=topic, facts=facts_block)),
        ]
        parsed = parse_json(llm.invoke(msgs).content, fallback={})
        for spec in parsed.get("tables", [])[:_TARGET_TABLES]:
            tbl = _clean_table(spec, len(tables) + 1, topic)
            if tbl:
                tables.append(tbl)
    except Exception as exc:
        logger.warning("Tables agent failed (%s); using fallback tables.", exc)

    # Ensure at least two tables exist.
    while len(tables) < _TARGET_TABLES:
        tables.append(_fallback_table(topic, facts, len(tables) + 1))

    emit(
        state,
        "writer",
        "completed",
        f"{len(tables)} table(s) ready: " + "; ".join(t["caption"] for t in tables),
    )
    return {"tables": tables}


def _clean_table(spec: dict, number: int, topic: str) -> dict | None:
    if not isinstance(spec, dict):
        return None
    cols = [str(c).strip() for c in spec.get("columns", []) if str(c).strip()]
    if not cols:
        return None

    cleaned_rows: list[list[str]] = []
    for row in spec.get("rows", []):
        if not isinstance(row, list):
            continue
        cells = [str(c).strip() for c in row]
        # Normalise to the column count.
        cells = (cells + [""] * len(cols))[: len(cols)]
        non_empty = sum(1 for c in cells if c)
        # Drop rows that are empty or mostly blank (e.g. a stray "2026" row).
        if non_empty < max(2, (len(cols) + 1) // 2):
            continue
        cleaned_rows.append(cells)

    if not cleaned_rows:
        return None
    return {
        "number": number,
        "caption": (spec.get("caption") or f"Summary of {topic}").strip(),
        "columns": cols,
        "rows": cleaned_rows[:6],
    }


def _fallback_table(topic: str, facts: list[dict], number: int) -> dict:
    # Use a different fact window per fallback table so they aren't identical.
    offset = (number - 1) * 5
    chunk = facts[offset : offset + 5] or facts[:5]
    rows = [[f"Aspect {i + 1}", f["text"][:80]] for i, f in enumerate(chunk)]
    return {
        "number": number,
        "caption": f"Key Findings on {topic}" if number == 1 else f"Further Aspects of {topic}",
        "columns": ["Aspect", "Finding"],
        "rows": rows or [["—", "No data"]],
    }
