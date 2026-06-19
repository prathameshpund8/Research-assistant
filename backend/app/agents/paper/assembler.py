"""Assembler agent — produces the final preview Markdown for the paper.

The structured fields (title, abstract, sections, references) remain available
for the .docx exporter; this node renders a human-readable Markdown view with
IEEE-style roman-numeral section numbering for the live preview.
"""

from __future__ import annotations

import logging

from app.agents._util import emit
from app.agents.state import ResearchState
from app.models.paper_schemas import float_placements

logger = logging.getLogger(__name__)

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def assembler_node(state: ResearchState) -> dict:
    title = state.get("paper_title", state["query"])
    authors = state.get("authors", []) or [{"name": "Anonymous Author"}]
    abstract = state.get("abstract", "")
    keywords = state.get("keywords", [])
    sections = state.get("sections", [])
    references = state.get("references", [])
    tables = state.get("tables", [])
    figures = state.get("figures", [])

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

    # Spread figures and tables evenly through the sections.
    placements = float_placements(len(sections), len(figures), len(tables))
    for i, sec in enumerate(sections):
        num = _ROMAN[i] if i < len(_ROMAN) else str(i + 1)
        lines += [f"## {num}.  {sec['heading'].upper()}", "", sec["body"], ""]
        for kind, idx in placements.get(i, []):
            if kind == "fig" and idx < len(figures):
                lines += [_figure_md(figures[idx]), ""]
            elif kind == "tbl" and idx < len(tables):
                lines += [_table_md(tables[idx]), ""]

    # No sections? Emit any floats before the references.
    for kind, idx in placements.get(-1, []):
        if kind == "fig" and idx < len(figures):
            lines += [_figure_md(figures[idx]), ""]
        elif kind == "tbl" and idx < len(tables):
            lines += [_table_md(tables[idx]), ""]

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
        f"Paper assembled: {len(sections)} sections, {len(tables)} table(s), "
        f"{len(figures)} figure(s), {len(references)} references.",
    )
    return {"paper_markdown": markdown}


_ROMAN_TBL = ["I", "II", "III", "IV", "V"]


def _table_md(tbl: dict) -> str:
    cols = tbl.get("columns", [])
    rows = tbl.get("rows", [])
    if not cols:
        return ""
    num = _ROMAN_TBL[(tbl.get("number", 1) - 1) % len(_ROMAN_TBL)]
    out = [f"**TABLE {num}. {tbl.get('caption', '').upper()}**", ""]
    out.append("| " + " | ".join(cols) + " |")
    out.append("| " + " | ".join("---" for _ in cols) + " |")
    for row in rows:
        cells = [str(c).replace("|", "\\|") for c in row]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _figure_md(fig: dict) -> str:
    """In-text figure caption. The actual image is rendered by the frontend
    (from structured data) and embedded in the .docx, so the Markdown only
    carries the IEEE caption reference."""
    return f"*Fig. {fig.get('number', 1)}. {fig.get('caption', '')}*"
