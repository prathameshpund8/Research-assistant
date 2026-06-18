"""In-memory research job manager.

Each ``POST /api/research`` creates a :class:`ResearchJob` that runs the
LangGraph in a background thread (``graph.invoke`` is synchronous). Agent nodes
emit progress events through a thread-safe callback; events are buffered on the
job so the SSE endpoint can replay history to late subscribers and then stream
live updates.

This is intentionally simple (single-process, in-memory). For production you'd
swap the store for Redis and the pub/sub for a real broker.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agents.graph import research_graph
from app.agents.state import new_state
from app.config import get_settings
from app.models.schemas import (
    AgentName,
    EventStatus,
    ExtractedFact,
    ProgressEvent,
    ResearchResult,
    Source,
)

logger = logging.getLogger(__name__)


@dataclass
class ResearchJob:
    id: str
    query: str
    status: str = "running"  # running | completed | error
    events: list[ProgressEvent] = field(default_factory=list)
    result: Optional[ResearchResult] = None
    finished: bool = False
    # Set lazily on the running loop; signals new events to SSE subscribers.
    _signal: Optional[asyncio.Event] = None

    def signal(self) -> asyncio.Event:
        if self._signal is None:
            self._signal = asyncio.Event()
        return self._signal


class JobManager:
    """Tracks research jobs for the lifetime of the process."""

    def __init__(self) -> None:
        self._jobs: dict[str, ResearchJob] = {}

    def get(self, job_id: str) -> Optional[ResearchJob]:
        return self._jobs.get(job_id)

    def start(self, query: str) -> ResearchJob:
        job = ResearchJob(id=uuid.uuid4().hex[:12], query=query)
        self._jobs[job.id] = job
        loop = asyncio.get_event_loop()
        # Run the (sync) graph off the event loop so SSE stays responsive.
        loop.create_task(self._run(job, loop))
        return job

    async def _run(self, job: ResearchJob, loop: asyncio.AbstractEventLoop) -> None:
        def emit(agent: str, status: str, message: str, data: dict[str, Any]) -> None:
            """Thread-safe progress callback handed to the graph state."""
            event = ProgressEvent(
                agent=_safe_agent(agent),
                status=_safe_status(status),
                message=message,
                data=data or {},
            )
            loop.call_soon_threadsafe(self._append_event, job, event)

        self._append_event(
            job,
            ProgressEvent(
                agent=AgentName.SYSTEM,
                status=EventStatus.STARTED,
                message=f"Research started for: {job.query!r}",
            ),
        )

        try:
            state = new_state(job.query, emit=emit)
            final = await asyncio.to_thread(research_graph.invoke, state)
            job.result = _state_to_result(job, final, status="completed")
            job.status = "completed"
            self._append_event(
                job,
                ProgressEvent(
                    agent=AgentName.SYSTEM,
                    status=EventStatus.COMPLETED,
                    message="Research complete.",
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Research job %s failed.", job.id)
            job.status = "error"
            job.result = ResearchResult(
                research_id=job.id, query=job.query, status="error", error=str(exc)
            )
            self._append_event(
                job,
                ProgressEvent(
                    agent=AgentName.SYSTEM,
                    status=EventStatus.ERROR,
                    message=f"Research failed: {exc}",
                ),
            )
        finally:
            job.finished = True
            job.signal().set()

    def _append_event(self, job: ResearchJob, event: ProgressEvent) -> None:
        job.events.append(event)
        sig = job.signal()
        sig.set()  # wake subscribers; they re-arm after draining.


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


def _state_to_result(job: ResearchJob, state: dict, status: str) -> ResearchResult:
    """Validate the raw graph state into the public ResearchResult model."""
    settings = get_settings()
    sources = [Source(**s) for s in state.get("sources", [])]
    facts = [
        ExtractedFact(text=f["text"], source_id=f["source_id"]) for f in state.get("facts", [])
    ]
    gaps = list(state.get("gaps", [])) + [
        f"[contradiction] {c}" for c in state.get("contradictions", [])
    ]
    return ResearchResult(
        research_id=job.id,
        query=job.query,
        status=status,
        sub_questions=state.get("sub_questions", []),
        sources=sources,
        facts=facts,
        gaps=gaps,
        rounds_used=min(state.get("round_count", 0), settings.max_research_rounds + 1),
        report_markdown=state.get("final_report", ""),
    )


# Process-wide singleton.
job_manager = JobManager()
