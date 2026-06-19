"""Assembler agent — produces the final preview Markdown for the paper.

The structured fields (title, abstract, sections, references) remain available
for the .docx exporter; this node renders a human-readable Markdown view with
IEEE-style roman-numeral section numbering for the live preview.
"""

from __future__ import annotations

import logging

from app.agents._util import emit
from app.agents.state import ResearchState

logger = logging.getLogger(__name__)

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def assembler_node(state: ResearchState) -> dict:
    title = state.get("paper_title", state["query"])
    authors = state.get("authors", []) or [{"name": "Anonymous Author"}]
    abstract = state.get("abstract", "")
    keywords = state.get("keywords", [])
    sections = state.get("sections", [])
    references = state.get("references", [])

    emit(state, "writer", "started", "Assembling the final paper preview.")

    lines: list[str] = [f"# {title}", ""]
    author_line = ", ".join(a.get("name", "Author") for a in authors)
    affil = "; ".join(
        filter(None, {f"{a.get('organization','')}".strip() for a in authors})
    )
    lines.append(f"*{author_line}*" + (f" — {affil}" if affil else ""))
    lines.append("")

    if abstract:
        lines += [f"**Abstract—{abstract}**", ""]
    if keywords:
        lines += [f"*Index Terms—{', '.join(keywords)}*", ""]

    for i, sec in enumerate(sections):
        num = _ROMAN[i] if i < len(_ROMAN) else str(i + 1)
        lines += [f"## {num}.  {sec['heading'].upper()}", "", sec["body"], ""]

    if references:
        lines += ["## References", ""]
        for ref in references:
            lines.append(f"[{ref['number']}] {ref['text']}")
            lines.append("")

    markdown = "\n".join(lines).strip() + "\n"
    emit(
        state,
        "writer",
        "completed",
        f"Paper assembled: {len(sections)} sections, {len(references)} references.",
    )
    return {"paper_markdown": markdown}
