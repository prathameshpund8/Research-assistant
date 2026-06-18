"""Pydantic models for the public REST API.

These are the request/response contracts shared with the Angular frontend.
The internal LangGraph "blackboard" state lives in ``app/agents/state.py``;
the models here are the serialisable, validated surface of that state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    """Body for ``POST /api/research``."""

    query: str = Field(min_length=3, max_length=500, description="Research topic / question.")


class ResearchAccepted(BaseModel):
    """Response acknowledging a started research job."""

    research_id: str
    status: str = "accepted"


# ---------------------------------------------------------------------------
# Core data objects (shared with the frontend)
# ---------------------------------------------------------------------------
class Source(BaseModel):
    """A single collected web source."""

    id: str = Field(description="Stable citation id, e.g. 'S1'.")
    title: str
    url: str
    snippet: str = ""
    sub_question: str = Field(default="", description="Sub-question this source answers.")
    score: float = 0.0


class ExtractedFact(BaseModel):
    """A fact extracted from a source, preserving attribution."""

    text: str
    source_id: str = Field(description="Maps back to Source.id — citation integrity.")


class AgentName(str, Enum):
    PLANNER = "planner"
    SEARCHER = "searcher"
    SUMMARIZER = "summarizer"
    CRITIC = "critic"
    WRITER = "writer"
    SYSTEM = "system"


class EventStatus(str, Enum):
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    ERROR = "error"


class ProgressEvent(BaseModel):
    """One streamed Server-Sent Event describing agent activity."""

    agent: AgentName
    status: EventStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------
class ResearchResult(BaseModel):
    """Response for ``GET /api/research/{id}`` once complete."""

    research_id: str
    query: str
    status: str  # running | completed | error
    sub_questions: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    rounds_used: int = 0
    report_markdown: str = ""
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthResponse(BaseModel):
    status: str
    version: str
    llm: dict[str, Any]
    search: dict[str, Any]
