"""Writer agent.

Synthesises the attributed facts into a structured, cited Markdown report:
an executive summary, thematic sections, an explicit note on any
contradictions/gaps, and a Sources list.

Citation integrity is enforced mechanically: the Writer is only given facts
that already carry a real ``source_id``, the prompt requires citing those ids,
and after generation we validate that every [S#] citation maps to a collected
source (unknown ones are stripped). URLs are never invented — the Sources
section is generated from the collected source list, not the model.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents._util import emit
from app.agents.state import ResearchState
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# === EDITABLE PROMPT =======================================================
WRITER_SYSTEM_PROMPT = """You are the Writer in a research system. Using ONLY
the provided facts, write a clear, well-structured Markdown research report.

Requirements:
- Start with a "## Executive Summary" (3-5 sentences).
- Then 2-4 thematic "## " sections with informative headings.
- EVERY claim must be followed by its citation(s) in square brackets using the
  given source ids, e.g. "Solar capacity grew sharply [S2][S5]."
- Do NOT introduce facts, numbers, or claims that are not in the provided list.
- Do NOT invent or write any URLs; citations are ids like [S1] only.
- If facts conflict, present BOTH sides and note the disagreement rather than
  choosing one.
- Do not write a Sources section — it is appended automatically.

Write the report body in Markdown now."""

WRITER_USER_TEMPLATE = (
    "Research topic: {query}\n\n"
    "Research plan: {plan}\n\n"
    "Facts (cite by source id):\n{facts}\n\n"
    "{gap_note}"
)
# ===========================================================================

_CITATION_RE = re.compile(r"\[(S\d+)\]")


def writer_node(state: ResearchState) -> dict:
    """LangGraph node: produce the final cited Markdown report."""
    query = state["query"]
    plan = state.get("plan", "")
    facts = state.get("facts", [])
    sources = state.get("sources", [])
    gaps = state.get("gaps", [])
    contradictions = state.get("contradictions", [])

    emit(state, "writer", "started", "Composing the cited report.")

    valid_ids = {s["id"] for s in sources}

    if not facts:
        body = (
            "## Executive Summary\n\n"
            f"No reliable facts could be gathered for **{query}**. "
            "Try a more specific query or configure a live search API key."
        )
    else:
        body = _compose_body(query, plan, facts, gaps, contradictions)
        body = _strip_unknown_citations(body, valid_ids)

    # Append a "Disagreements & Gaps" note so they're never silently dropped.
    notes = _build_notes(contradictions, gaps)

    # Build the Sources section ourselves — guarantees real URLs only, and
    # only for sources actually cited in the body (citation integrity).
    sources_md = _build_sources_section(body + notes, sources)

    report = f"# Research Report: {query}\n\n{body}\n{notes}\n{sources_md}".strip() + "\n"

    cited = set(_CITATION_RE.findall(body))
    emit(
        state,
        "writer",
        "completed",
        f"Report ready: {len(cited)} distinct citation(s), {len(sources)} source(s).",
        cited_count=len(cited),
        source_count=len(sources),
    )
    return {"final_report": report}


def _compose_body(query, plan, facts, gaps, contradictions) -> str:
    facts_text = "\n".join(f"- [{f['source_id']}] {f['text']}" for f in facts)
    gap_note = ""
    if contradictions:
        gap_note += "Known contradictions to address in the report:\n" + "\n".join(
            f"- {c}" for c in contradictions
        )
    try:
        llm = get_llm(temperature=0.3)
        messages = [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            HumanMessage(
                content=WRITER_USER_TEMPLATE.format(
                    query=query, plan=plan, facts=facts_text, gap_note=gap_note
                )
            ),
        ]
        return llm.invoke(messages).content.strip()
    except Exception as exc:
        logger.warning("Writer LLM unavailable (%s); building deterministic report.", exc)
        return _fallback_body(query, facts)


def _fallback_body(query: str, facts: list[dict]) -> str:
    """Deterministic report when the LLM is unavailable — still fully cited."""
    lines = [
        "## Executive Summary",
        "",
        f"The following findings about **{query}** were gathered from the "
        "collected sources. (Generated without an LLM; facts are listed verbatim "
        "with their citations.)",
        "",
        "## Findings",
        "",
    ]
    for f in facts:
        lines.append(f"- {f['text']} [{f['source_id']}]")
    return "\n".join(lines)


def _strip_unknown_citations(body: str, valid_ids: set[str]) -> str:
    """Remove citations that don't map to a real collected source."""

    def repl(match: re.Match) -> str:
        return match.group(0) if match.group(1) in valid_ids else ""

    return _CITATION_RE.sub(repl, body)


def _build_notes(contradictions: list[str], gaps: list[str]) -> str:
    if not contradictions and not gaps:
        return ""
    out = ["\n## Disagreements & Open Gaps\n"]
    if contradictions:
        out.append("**Contradictions found across sources:**\n")
        out.extend(f"- {c}" for c in contradictions)
        out.append("")
    if gaps:
        out.append("**Aspects with limited coverage:**\n")
        out.extend(f"- {g}" for g in gaps)
        out.append("")
    return "\n".join(out)


def _build_sources_section(text: str, sources: list[dict]) -> str:
    """Render only the sources actually cited in the text, with real URLs."""
    cited = set(_CITATION_RE.findall(text))
    used = [s for s in sources if s["id"] in cited] or sources
    if not used:
        return "\n## Sources\n\n_No sources collected._\n"
    lines = ["\n## Sources\n"]
    for s in used:
        lines.append(f"- **[{s['id']}]** [{s['title']}]({s['url']})")
    return "\n".join(lines) + "\n"
