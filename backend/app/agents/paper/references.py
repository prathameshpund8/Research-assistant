"""References agent.

Collects the sources actually cited across the finished sections, assigns IEEE
reference numbers in order of first appearance, rewrites the in-text ``[S#]``
markers to ``[n]``, and formats an IEEE-style reference list. URLs come straight
from the collected sources — never invented (citation integrity).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.agents._util import emit
from app.agents.state import ResearchState

logger = logging.getLogger(__name__)

_CITE = re.compile(r"\[(S\d+)\]")


def references_node(state: ResearchState) -> dict:
    sections = state.get("sections", [])
    sources = {s["id"]: s for s in state.get("sources", [])}

    emit(state, "writer", "started", "Formatting IEEE references and numbering citations.")

    # Order of first appearance across all section bodies.
    order: list[str] = []
    for sec in sections:
        for sid in _CITE.findall(sec["body"]):
            if sid in sources and sid not in order:
                order.append(sid)

    mapping = {sid: i + 1 for i, sid in enumerate(order)}

    # Rewrite [S#] -> [n] in each section.
    def renumber(body: str) -> str:
        return _CITE.sub(lambda m: f"[{mapping[m.group(1)]}]" if m.group(1) in mapping else "", body)

    new_sections = [{"heading": s["heading"], "body": renumber(s["body"])} for s in sections]

    today = datetime.now(timezone.utc).strftime("%b. %d, %Y")
    references = []
    for sid in order:
        src = sources[sid]
        references.append(
            {
                "number": mapping[sid],
                "source_id": sid,
                "text": _format_ieee(src, today),
                "url": src.get("url", ""),
            }
        )

    emit(
        state,
        "writer",
        "completed",
        f"Built {len(references)} IEEE reference(s) from cited sources.",
        references=len(references),
    )
    return {"sections": new_sections, "references": references}


def _format_ieee(src: dict, accessed: str) -> str:
    """IEEE-style online reference: \"Title,\" Site. [Online]. Available: URL."""
    title = (src.get("title") or "Untitled").strip().strip(".")
    url = src.get("url", "")
    site = urlparse(url).netloc.replace("www.", "") if url else ""
    site_part = f" {site}." if site else ""
    return f'"{title},"{site_part} [Online]. Available: {url}. [Accessed: {accessed}].'
