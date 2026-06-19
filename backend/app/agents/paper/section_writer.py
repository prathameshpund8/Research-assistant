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
SECTION_SYSTEM_PROMPT = """You are writing one section of a full-length (6-7 page)
IEEE conference paper. Use ONLY the provided facts; do not invent facts, numbers,
or citations.

Rules:
- Write formal, academic IEEE prose (third person, present tense where natural).
- LENGTH IS IMPORTANT: write AT LEAST 4 well-developed paragraphs
  (about 350-550 words total). Each paragraph should be 4-6 sentences. Develop
  the ideas fully with explanation, context, examples, and analysis.
- Synthesise and EXPLAIN the facts in your own words — do NOT copy source
  wording. Paraphrase; connect ideas; compare viewpoints; elaborate.
- Cite every factual claim with the source ids in square brackets, e.g. [S3][S7].
- Use 2-3 "**A. Subsection Title**" bold subsections to organise and expand the
  section into distinct themes.
- Do not repeat the section heading. Avoid bullet lists unless truly apt.
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


# Cap how many facts go into each section prompt. Sending *all* facts (often
# 50-100) makes each call ~8k tokens, which blows the per-minute token limit and
# forces a fallback. A focused subset keeps calls small so they succeed.
_MAX_FACTS_PER_SECTION = 22


def section_writer_node(state: ResearchState) -> dict:
    title = state.get("paper_title", state["query"])
    plan = state.get("section_plan", [])
    facts = state.get("facts", [])

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
    for i, spec in enumerate(plan):
        heading = spec["heading"]
        emit(state, "writer", "progress", f"Writing section: {heading}")
        # Give each section a different window of facts (less repetition + a
        # smaller prompt that stays under the per-minute token limit).
        section_facts = _facts_block(facts, start=i * _MAX_FACTS_PER_SECTION)
        if llm_ok:
            try:
                msgs = [
                    SystemMessage(content=SECTION_SYSTEM_PROMPT),
                    HumanMessage(
                        content=SECTION_USER_TEMPLATE.format(
                            title=title,
                            heading=heading,
                            guidance=spec.get("guidance", ""),
                            facts=section_facts,
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


def _facts_block(facts: list[dict], start: int = 0) -> str:
    """A size-capped, rotated window of facts for one section's prompt."""
    if not facts:
        return "(no facts)"
    n = len(facts)
    count = min(_MAX_FACTS_PER_SECTION, n)
    window = [facts[(start + i) % n] for i in range(count)]
    return "\n".join(f"- ({f['source_id']}) {f['text'][:240]}" for f in window)


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
