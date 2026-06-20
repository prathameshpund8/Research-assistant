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
from app.services.llm import get_fast_llm, get_llm

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

    # Tiered models: prefer the strong 70B model, but fall back to the cheaper
    # fast model when the 70B is rate-limited/exhausted (its daily budget is
    # separate). This keeps sections as real multi-paragraph prose instead of
    # dropping to the one-line stub.
    primary = _try_build(get_llm, 0.35)
    fast = _try_build(get_fast_llm, 0.4)
    used_fast = False

    sections: list[dict] = []
    for i, spec in enumerate(plan):
        heading = spec["heading"]
        emit(state, "writer", "progress", f"Writing section: {heading}")
        # Give each section a different window of facts (less repetition + a
        # smaller prompt that stays under the per-minute token limit).
        section_facts = _facts_block(facts, start=i * _MAX_FACTS_PER_SECTION)
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
        body, from_fast = _write(primary, fast, msgs)
        if body is None:
            body = _fallback_section(heading, facts)
        used_fast = used_fast or from_fast
        sections.append({"heading": heading, "body": body})

    if used_fast:
        emit(state, "writer", "progress", "Primary model rate-limited; used the fast model for some sections.")

    # Abstract from the finished sections.
    abstract = _write_abstract(primary, fast, title, sections)

    emit(state, "writer", "completed", f"Drafted {len(sections)} sections and the abstract.")
    return {"sections": sections, "abstract": abstract}


def _try_build(factory, temperature: float):
    try:
        return factory(temperature=temperature)
    except Exception as exc:  # no key configured
        logger.warning("LLM unavailable (%s).", exc)
        return None


def _write(primary, fast, msgs) -> tuple[str | None, bool]:
    """Try the primary model, then the fast model. Returns (text, used_fast)."""
    for llm, is_fast in ((primary, False), (fast, True)):
        if llm is None:
            continue
        try:
            text = llm.invoke(msgs).content.strip()
            if text:
                return text, is_fast
        except Exception as exc:
            logger.warning("%s model failed for a section (%s); trying next.",
                           "fast" if is_fast else "primary", str(exc)[:80])
    return None, False


def _facts_block(facts: list[dict], start: int = 0) -> str:
    """A size-capped, rotated window of facts for one section's prompt."""
    if not facts:
        return "(no facts)"
    n = len(facts)
    count = min(_MAX_FACTS_PER_SECTION, n)
    window = [facts[(start + i) % n] for i in range(count)]
    return "\n".join(f"- ({f['source_id']}) {f['text'][:240]}" for f in window)


def _write_abstract(primary, fast, title: str, sections: list[dict]) -> str:
    summaries = "\n".join(f"{s['heading']}: {s['body'][:240]}" for s in sections)
    msgs = [
        SystemMessage(content=ABSTRACT_SYSTEM_PROMPT),
        HumanMessage(content=ABSTRACT_USER_TEMPLATE.format(title=title, summaries=summaries)),
    ]
    text, _ = _write(primary, fast, msgs)
    if text:
        return text
    return f"This paper examines {title} based on a review of the collected sources."


def _fallback_section(heading: str, facts: list[dict]) -> str:
    lines = [f"This section addresses {heading.lower()}."]
    for f in facts[:4]:
        lines.append(f"{f['text']} [{f['source_id']}]")
    return " ".join(lines)
