"""Pydantic models for the IEEE paper generator.

These describe the structured paper that the paper-pipeline agents build and
that the frontend renders (preview) / exports (.docx).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------
class Author(BaseModel):
    name: str = "Anonymous Author"
    department: str = "Dept. of Research"
    organization: str = "Institution"
    city: str = ""
    email: str = ""


class PaperRequest(BaseModel):
    """Body for ``POST /api/paper``."""

    topic: str = Field(min_length=3, max_length=300)
    details: str = Field(default="", max_length=2000, description="Optional scope/specifics.")
    authors: list[Author] = Field(default_factory=lambda: [Author()])


class PaperAccepted(BaseModel):
    paper_id: str
    status: str = "accepted"


# ---------------------------------------------------------------------------
# Structured paper
# ---------------------------------------------------------------------------
class PaperSection(BaseModel):
    """One numbered IEEE section (its subsections are inlined as Markdown)."""

    heading: str
    body: str  # Markdown; citations as [n] after the references pass.


class Reference(BaseModel):
    number: int  # IEEE [n]
    source_id: str  # original S# it maps to
    text: str  # formatted IEEE reference line
    url: str


class PaperTable(BaseModel):
    number: int = 1
    caption: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class PaperFigure(BaseModel):
    number: int = 1
    caption: str = ""
    image_base64: str = ""  # PNG bytes, base64 (no data: prefix)


class FlaggedPassage(BaseModel):
    section: str
    passage: str
    source_id: str
    similarity: float  # 0..1 overlap before rewriting


class OriginalityReport(BaseModel):
    score: float = 100.0  # 0..100 post-paraphrase originality
    pre_score: float = 100.0  # originality before paraphrasing
    flagged: list[FlaggedPassage] = Field(default_factory=list)
    rewritten: int = 0
    still_flagged: int = 0  # passages still above threshold after paraphrase
    method: str = "n-gram overlap vs. retrieved source text + LLM paraphrase"


class VerificationReport(BaseModel):
    total_claims: int = 0
    supported_claims: int = 0
    unsupported_removed: int = 0
    notes: list[str] = Field(default_factory=list)


class PaperResult(BaseModel):
    paper_id: str
    topic: str
    details: str = ""
    status: str  # running | completed | error
    title: str = ""
    authors: list[Author] = Field(default_factory=list)
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    sections: list[PaperSection] = Field(default_factory=list)
    tables: list[PaperTable] = Field(default_factory=list)
    figures: list[PaperFigure] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    originality: OriginalityReport = Field(default_factory=OriginalityReport)
    verification: VerificationReport = Field(default_factory=VerificationReport)
    paper_markdown: str = ""
    rounds_used: int = 0
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
