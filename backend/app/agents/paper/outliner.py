"""Outliner agent — the Planner for the paper pipeline.

From the topic (+ optional details) it produces:
  - a publishable paper title,
  - index terms / keywords,
  - an IEEE section plan (Introduction, Related Work, ...),
  - research sub-questions (so the existing Searcher/Summarizer can gather
    grounded sources before any section is written).
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit, parse_json
from app.agents.state import ResearchState
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
OUTLINER_SYSTEM_PROMPT = """You are the Outliner for a full-length (6-7 page)
IEEE-format **literature review / survey** paper (NOT an original empirical
study). Given a topic and optional scope, produce a JSON plan with 7-8 sections
suited to a survey that synthesises existing published sources.

IMPORTANT: This is a review of existing literature. Do NOT include sections that
imply original experiments — no "Data Collection", "Experiments", or "Statistical
Analysis". Use review-style sections instead.

Return STRICT JSON only:
{
  "title": "<survey/review title; you may start with 'A Review of' or 'A Survey of', Title Case>",
  "keywords": ["<4-6 index terms>"],
  "sections": [
    {"heading": "Introduction", "guidance": "<motivation, scope, why a review matters>"},
    {"heading": "Background", "guidance": "..."},
    {"heading": "Review Methodology", "guidance": "scope of the review and how the literature is organised (NOT data collection)"},
    {"heading": "<Thematic heading, e.g. Approaches/Applications>", "guidance": "..."},
    {"heading": "<Thematic heading, e.g. Findings Across the Literature>", "guidance": "..."},
    {"heading": "Challenges and Limitations", "guidance": "..."},
    {"heading": "Discussion and Future Directions", "guidance": "..."},
    {"heading": "Conclusion", "guidance": "..."}
  ],
  "sub_questions": ["<7-9 research questions to investigate the topic deeply>"]
}
No text outside the JSON."""

OUTLINER_USER_TEMPLATE = "Topic: {topic}\n\nScope / details (may be empty):\n{details}"
# ===========================================================================

DEFAULT_SECTIONS = [
    {"heading": "Introduction", "guidance": "Motivate the topic and the value of a review; state scope."},
    {"heading": "Background", "guidance": "Define core concepts and necessary preliminaries."},
    {"heading": "Review Methodology", "guidance": "Describe the scope of the review and how the literature is organised (not data collection)."},
    {"heading": "Approaches and Applications", "guidance": "Survey the main approaches, methods, and use cases reported in the literature."},
    {"heading": "Findings Across the Literature", "guidance": "Synthesise what published studies report; compare and contrast results."},
    {"heading": "Challenges and Limitations", "guidance": "Discuss open problems, risks, trade-offs noted in the literature."},
    {"heading": "Discussion and Future Directions", "guidance": "Synthesise implications and future research directions."},
    {"heading": "Conclusion", "guidance": "Summarise the state of the literature and outlook."},
]


def outliner_node(state: ResearchState) -> dict:
    topic = state["query"]
    details = state.get("details", "")
    emit(state, "planner", "started", f"Outlining IEEE paper for: {topic!r}")

    parsed: dict = {}
    try:
        llm = get_llm(temperature=0.3)
        messages = [
            SystemMessage(content=OUTLINER_SYSTEM_PROMPT),
            HumanMessage(content=OUTLINER_USER_TEMPLATE.format(topic=topic, details=details or "(none)")),
        ]
        parsed = parse_json(llm.invoke(messages).content, fallback={})
    except Exception as exc:
        logger.warning("Outliner LLM failed (%s); using default outline.", exc)
        emit(state, "planner", "progress", f"LLM unavailable ({exc}); using a default IEEE outline.")

    title = (parsed.get("title") or f"A Review of {topic}").strip()
    keywords = [k.strip() for k in parsed.get("keywords", []) if isinstance(k, str) and k.strip()]
    if not keywords:
        keywords = [topic.lower(), "survey", "analysis"]

    sections = parsed.get("sections") or []
    section_plan = [
        {"heading": s["heading"].strip(), "guidance": (s.get("guidance") or "").strip()}
        for s in sections
        if isinstance(s, dict) and s.get("heading")
    ] or DEFAULT_SECTIONS

    sub_questions = [q.strip() for q in parsed.get("sub_questions", []) if isinstance(q, str) and q.strip()]
    if len(sub_questions) < 3:
        sub_questions = [
            f"What is {topic} and why does it matter?",
            f"What background and core concepts underpin {topic}?",
            f"What are the key methods, components, or data of {topic}?",
            f"What prior work and approaches exist for {topic}?",
            f"What are the main applications and use cases of {topic}?",
            f"What are the challenges, limitations, or open problems in {topic}?",
            f"What are recent advances and the current state of {topic}?",
        ]

    emit(
        state,
        "planner",
        "completed",
        f"Outline ready: '{title}' — {len(section_plan)} sections, {len(sub_questions)} research questions.",
        title=title,
        sections=[s["heading"] for s in section_plan],
    )
    return {
        "paper_title": title,
        "keywords": keywords[:6],
        "section_plan": section_plan,
        "sub_questions": sub_questions[:9],
        "plan": f"IEEE paper on {topic}",
    }
