"""Figures agent — generates two diagrams for the paper.

Asks the LLM for two figure specs (e.g. a process flow and a concept map) and
renders each to a PNG with matplotlib. Falls back to diagrams built from the
section plan / keywords if the LLM is unavailable.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.services.figure_gen import render_spec
from app.services.llm import get_fast_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
FIGURE_SYSTEM_PROMPT = """You design TWO simple diagrams for an IEEE paper. Make
them DIFFERENT: ideally one "flow" (3-6 ordered steps of a process/method) and
one "concept" (a central concept with 3-6 related aspects).

Return STRICT JSON only:
{
  "figures": [
    {"caption": "...", "kind": "flow", "nodes": ["...","..."]},
    {"caption": "...", "kind": "concept", "center": "...", "nodes": ["...","..."]}
  ]
}
Keep labels short (<= 5 words). No text outside the JSON."""

FIGURE_USER_TEMPLATE = "Topic: {topic}\n\nKey facts:\n{facts}"
# ===========================================================================

_TARGET_FIGURES = 2


def figures_node(state: ResearchState) -> dict:
    topic = state.get("paper_title", state["query"])
    facts = state.get("facts", [])
    facts_block = "\n".join(f"- {f['text']}" for f in facts[:20]) or "(none)"

    emit(state, "writer", "started", "Generating diagrams (figures).")

    specs: list[dict] = []
    try:
        llm = get_fast_llm(temperature=0.3)
        msgs = [
            SystemMessage(content=FIGURE_SYSTEM_PROMPT),
            HumanMessage(content=FIGURE_USER_TEMPLATE.format(topic=topic, facts=facts_block)),
        ]
        parsed = parse_json(llm.invoke(msgs).content, fallback={})
        specs = [s for s in parsed.get("figures", []) if isinstance(s, dict) and s.get("nodes")]
    except Exception as exc:
        logger.warning("Figures agent LLM failed (%s); using heading-based diagrams.", exc)

    specs = specs[:_TARGET_FIGURES]
    # Top up to two figures with sensible defaults.
    headings = [s["heading"] for s in state.get("section_plan", [])][:5]
    keywords = state.get("keywords", [])[:5]
    defaults = [
        {"kind": "flow", "caption": f"Workflow of {topic}",
         "nodes": headings or ["Background", "Approach", "Analysis", "Conclusion"]},
        {"kind": "concept", "caption": f"Key Aspects of {topic}", "center": topic,
         "nodes": keywords or ["Methods", "Applications", "Challenges", "Future"]},
    ]
    for d in defaults:
        if len(specs) >= _TARGET_FIGURES:
            break
        specs.append(d)

    figures: list[dict] = []
    for spec in specs:
        image_b64 = render_spec(spec)
        if not image_b64:
            continue
        figures.append(
            {
                "number": len(figures) + 1,
                "caption": (spec.get("caption") or f"Overview of {topic}").strip(),
                "image_base64": image_b64,
            }
        )

    emit(state, "writer", "completed", f"{len(figures)} figure(s) ready.")
    return {"figures": figures}
