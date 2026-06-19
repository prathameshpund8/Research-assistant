"""Verifier agent — enforces citation integrity across the drafted sections.

Every ``[S#]`` citation must map to a real collected source; unknown ones are
stripped (the model occasionally cites an id it was not given). We also flag
sections that contain factual-looking prose with no citation at all.
"""

from __future__ import annotations

import logging
import re

from app.agents._util import emit
from app.agents.state import ResearchState

logger = logging.getLogger(__name__)

_CITE = re.compile(r"\[(S\d+)\]")


def verifier_node(state: ResearchState) -> dict:
    sections = state.get("sections", [])
    valid_ids = {s["id"] for s in state.get("sources", [])}

    emit(state, "critic", "started", "Verifying every claim maps to a real source.")

    total_citations = 0
    supported = 0
    removed = 0
    notes: list[str] = []
    cleaned: list[dict] = []

    for sec in sections:
        body = sec["body"]
        cites = _CITE.findall(body)
        total_citations += len(cites)

        def repl(m: re.Match) -> str:
            nonlocal supported, removed
            if m.group(1) in valid_ids:
                supported += 1
                return m.group(0)
            removed += 1
            return ""

        new_body = _CITE.sub(repl, body)
        if not _CITE.search(new_body) and len(new_body.split()) > 40:
            notes.append(f"Section '{sec['heading']}' has limited inline citations.")
        cleaned.append({"heading": sec["heading"], "body": new_body})

    verification = {
        "total_claims": total_citations,
        "supported_claims": supported,
        "unsupported_removed": removed,
        "notes": notes,
    }
    emit(
        state,
        "critic",
        "completed",
        f"Verified {supported}/{total_citations} citations; removed {removed} invalid.",
        **verification,
    )
    return {"sections": cleaned, "verification": verification}
