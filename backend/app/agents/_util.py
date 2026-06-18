"""Small helpers shared by the agent nodes."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.state import ResearchState

logger = logging.getLogger(__name__)


def emit(state: ResearchState, agent: str, status: str, message: str, **data: Any) -> None:
    """Fire a progress event via the callback stored on the state (if any)."""
    cb = state.get("emit")
    if cb is not None:
        try:
            cb(agent, status, message, data)
        except Exception:  # never let event plumbing break the graph
            logger.exception("Progress emit failed for %s/%s", agent, status)


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json(text: str, fallback: Any) -> Any:
    """Best-effort JSON extraction from an LLM response.

    Models sometimes wrap JSON in markdown fences or add prose. We try the raw
    string, then any fenced block, then the first {...}/[...] span. On total
    failure we return ``fallback`` so the pipeline degrades instead of crashing.
    """
    candidates: list[str] = [text.strip()]

    fenced = _JSON_BLOCK.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())

    # Greedy span between first opening and last closing bracket.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue

    logger.warning("Could not parse JSON from LLM output; using fallback.")
    return fallback
