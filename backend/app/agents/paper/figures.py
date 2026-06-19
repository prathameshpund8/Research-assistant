"""Figures agent — generates one diagram for the paper.

Asks the LLM for a small figure spec (a process flow or a concept map of the
topic's key ideas) and renders it to a PNG with matplotlib. Falls back to a
flow diagram built from the section headings if the LLM is unavailable.
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
FIGURE_SYSTEM_PROMPT = """You design ONE simple diagram for an IEEE paper.
Pick the most useful of:
  - "flow": 3-6 ordered steps of a process/method/pipeline, or
  - "concept": a central concept with 3-6 related aspects.

Return STRICT JSON only:
{
  "caption": "<figure caption>",
  "kind": "flow" | "concept",
  "center": "<central label, only for concept>",
  "nodes": ["<label1>", "<label2>", "..."]
}
Keep labels short (<= 5 words). No text outside the JSON."""

FIGURE_USER_TEMPLATE = "Topic: {topic}\n\nKey facts:\n{facts}"
# ===========================================================================


def figures_node(state: ResearchState) -> dict:
    topic = state.get("paper_title", state["query"])
    facts = state.get("facts", [])
    facts_block = "\n".join(f"- {f['text']}" for f in facts[:20]) or "(none)"

    emit(state, "writer", "started", "Generating a diagram (figure).")

    spec: dict = {}
    try:
        llm = get_fast_llm(temperature=0.3)
        msgs = [
            SystemMessage(content=FIGURE_SYSTEM_PROMPT),
            HumanMessage(content=FIGURE_USER_TEMPLATE.format(topic=topic, facts=facts_block)),
        ]
        spec = parse_json(llm.invoke(msgs).content, fallback={})
    except Exception as exc:
        logger.warning("Figures agent LLM failed (%s); using heading-based flow.", exc)

    if not spec.get("nodes"):
        spec = {
            "kind": "flow",
            "caption": f"Conceptual overview of {topic}",
            "nodes": [s["heading"] for s in state.get("section_plan", [])][:5]
            or ["Background", "Approach", "Analysis", "Conclusion"],
        }

    image_b64 = render_spec(spec)
    if not image_b64:
        emit(state, "writer", "completed", "Figure generation skipped (render failed).")
        return {"figures": []}

    figure = {
        "number": 1,
        "caption": (spec.get("caption") or f"Overview of {topic}").strip(),
        "image_base64": image_b64,
    }
    emit(state, "writer", "completed", f"Figure ready: '{figure['caption']}'.")
    return {"figures": [figure]}
