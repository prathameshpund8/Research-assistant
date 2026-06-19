"""Section Writer agent.

Writes each planned IEEE section as grounded prose, citing collected sources by
their ``[S#]`` id, then writes the Abstract last (from the finished sections).
Only facts gathered by the Summarizer are used — no outside claims — so every
sentence can be traced to a real source.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit
from app.agents.state import ResearchState
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPTS ======================================================
SECTION_SYSTEM_PROMPT = """You are writing one section of an IEEE conference paper.
Use ONLY the provided facts; do not invent facts, numbers, or citations.

Rules:
- Write formal, academic IEEE prose (third person, present tense where natural).
- Cite every factual claim with the source ids in square brackets, e.g. [S3][S7].
- You MAY use "A. Subsection Title" markdown-style bold subsections if helpful.
- 2-4 paragraphs. Do not repeat the section heading. No bullet lists unless apt.
- Do NOT write citations you were not given; only use the listed source ids."""

SECTION_USER_TEMPLATE = (
    "Paper title: {title}\n"
    "Section: {heading}\n"
    "What this section must cover: {guidance}\n\n"
    "Facts you may cite (source id in parentheses):\n{facts}\n\n"
    "Write the section body now (Markdown, with [S#] citations)."
)

ABSTRACT_SYSTEM_PROMPT = """You write the Abstract of an IEEE conference paper.
Write a single paragraph (120-200 words): context, problem, approach, key
findings, and significance. Formal tone. No citations in the abstract. Output
only the abstract text."""

ABSTRACT_USER_TEMPLATE = "Paper title: {title}\n\nSection summaries:\n{summaries}"
# ===========================================================================


def section_writer_node(state: ResearchState) -> dict:
    title = state.get("paper_title", state["query"])
    plan = state.get("section_plan", [])
    facts = state.get("facts", [])
    facts_block = "\n".join(f"- ({f['source_id']}) {f['text']}" for f in facts) or "(no facts)"

    emit(state, "writer", "started", f"Drafting {len(plan)} sections from {len(facts)} facts.")

    try:
        llm = get_llm(temperature=0.35)
        llm_ok = True
    except Exception as exc:
        logger.warning("Section writer LLM unavailable (%s).", exc)
        emit(state, "writer", "progress", f"LLM unavailable ({exc}); writing minimal sections.")
        llm = None
        llm_ok = False

    sections: list[dict] = []
    for spec in plan:
        heading = spec["heading"]
        emit(state, "writer", "progress", f"Writing section: {heading}")
        if llm_ok:
            try:
                msgs = [
                    SystemMessage(content=SECTION_SYSTEM_PROMPT),
                    HumanMessage(
                        content=SECTION_USER_TEMPLATE.format(
                            title=title,
                            heading=heading,
                            guidance=spec.get("guidance", ""),
                            facts=facts_block,
                        )
                    ),
                ]
                body = llm.invoke(msgs).content.strip()
            except Exception:
                logger.exception("Failed writing section %s.", heading)
                body = _fallback_section(heading, facts)
        else:
            body = _fallback_section(heading, facts)
        sections.append({"heading": heading, "body": body})

    # Abstract from the finished sections.
    abstract = _write_abstract(llm if llm_ok else None, title, sections)

    emit(state, "writer", "completed", f"Drafted {len(sections)} sections and the abstract.")
    return {"sections": sections, "abstract": abstract}


def _write_abstract(llm, title: str, sections: list[dict]) -> str:
    summaries = "\n".join(f"{s['heading']}: {s['body'][:240]}" for s in sections)
    if llm is None:
        return (
            f"This paper examines {title}. It surveys the relevant literature, "
            "describes the approach, and discusses the main findings and their "
            "implications based on the collected sources."
        )
    try:
        msgs = [
            SystemMessage(content=ABSTRACT_SYSTEM_PROMPT),
            HumanMessage(content=ABSTRACT_USER_TEMPLATE.format(title=title, summaries=summaries)),
        ]
        return llm.invoke(msgs).content.strip()
    except Exception:
        logger.exception("Abstract generation failed; using fallback.")
        return f"This paper examines {title} based on a review of collected sources."


def _fallback_section(heading: str, facts: list[dict]) -> str:
    lines = [f"This section addresses {heading.lower()}."]
    for f in facts[:4]:
        lines.append(f"{f['text']} [{f['source_id']}]")
    return " ".join(lines)
