"""Background job manager for the IEEE paper pipeline.

Mirrors ``services/jobs.py`` (in-memory job + buffered SSE events) but runs the
paper graph and produces a :class:`PaperResult`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agents.paper.graph import paper_graph
from app.agents.state import new_state
from app.config import get_settings
from app.models.paper_schemas import (
    Author,
    OriginalityReport,
    PaperResult,
    PaperSection,
    Reference,
    VerificationReport,
)
from app.models.schemas import AgentName, EventStatus, ProgressEvent

logger = logging.getLogger(__name__)


@dataclass
class PaperJob:
    id: str
    topic: str
    details: str
    authors: list[dict]
    status: str = "running"
    events: list[ProgressEvent] = field(default_factory=list)
    result: Optional[PaperResult] = None
    finished: bool = False
    _signal: Optional[asyncio.Event] = None

    def signal(self) -> asyncio.Event:
        if self._signal is None:
            self._signal = asyncio.Event()
        return self._signal


class PaperJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, PaperJob] = {}

    def get(self, job_id: str) -> Optional[PaperJob]:
        return self._jobs.get(job_id)

    def start(self, topic: str, details: str, authors: list[dict]) -> PaperJob:
        job = PaperJob(id=uuid.uuid4().hex[:12], topic=topic, details=details, authors=authors)
        self._jobs[job.id] = job
        loop = asyncio.get_event_loop()
        loop.create_task(self._run(job, loop))
        return job

    async def _run(self, job: PaperJob, loop: asyncio.AbstractEventLoop) -> None:
        def emit(agent: str, status: str, message: str, data: dict[str, Any]) -> None:
            event = ProgressEvent(
                agent=_safe_agent(agent),
                status=_safe_status(status),
                message=message,
                data=data or {},
            )
            loop.call_soon_threadsafe(self._append, job, event)

        self._append(
            job,
            ProgressEvent(
                agent=AgentName.SYSTEM,
                status=EventStatus.STARTED,
                message=f"Paper generation started for: {job.topic!r}",
            ),
        )
        try:
            state = new_state(job.topic, emit=emit)
            state["details"] = job.details
            state["authors"] = job.authors
            final = await asyncio.to_thread(paper_graph.invoke, state)
            job.result = _state_to_paper(job, final)
            job.status = "completed"
            self._append(
                job,
                ProgressEvent(
                    agent=AgentName.SYSTEM,
                    status=EventStatus.COMPLETED,
                    message="Paper ready.",
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Paper job %s failed.", job.id)
            job.status = "error"
            job.result = PaperResult(
                paper_id=job.id, topic=job.topic, details=job.details, status="error", error=str(exc)
            )
            self._append(
                job,
                ProgressEvent(
                    agent=AgentName.SYSTEM,
                    status=EventStatus.ERROR,
                    message=f"Paper generation failed: {exc}",
                ),
            )
        finally:
            job.finished = True
            job.signal().set()

    def _append(self, job: PaperJob, event: ProgressEvent) -> None:
        job.events.append(event)
        job.signal().set()


def _safe_agent(name: str) -> AgentName:
    try:
        return AgentName(name)
    except ValueError:
        return AgentName.SYSTEM


def _safe_status(name: str) -> EventStatus:
    try:
        return EventStatus(name)
    except ValueError:
        return EventStatus.PROGRESS


def _state_to_paper(job: PaperJob, state: dict) -> PaperResult:
    settings = get_settings()
    authors = [Author(**a) if isinstance(a, dict) else Author() for a in state.get("authors", [])]
    sections = [PaperSection(**s) for s in state.get("sections", [])]
    references = [Reference(**r) for r in state.get("references", [])]
    originality = OriginalityReport(**state["originality"]) if state.get("originality") else OriginalityReport()
    verification = (
        VerificationReport(**state["verification"]) if state.get("verification") else VerificationReport()
    )
    return PaperResult(
        paper_id=job.id,
        topic=job.topic,
        details=job.details,
        status="completed",
        title=state.get("paper_title", ""),
        authors=authors,
        abstract=state.get("abstract", ""),
        keywords=state.get("keywords", []),
        sections=sections,
        references=references,
        originality=originality,
        verification=verification,
        paper_markdown=state.get("paper_markdown", ""),
        rounds_used=min(state.get("round_count", 0), settings.max_research_rounds + 1),
    )


paper_job_manager = PaperJobManager()
