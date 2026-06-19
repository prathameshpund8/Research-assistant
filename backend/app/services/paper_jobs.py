"""Background job manager for the IEEE paper pipeline.

Mirrors ``services/jobs.py`` (in-memory job + buffered SSE events) but runs the
paper graph and produces a :class:`PaperResult`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.agents.paper.graph import paper_graph
from app.agents.state import new_state
from app.config import get_settings
from app.models.paper_schemas import (
    Author,
    OriginalityReport,
    PaperFigure,
    PaperResult,
    PaperSection,
    PaperTable,
    Reference,
    VerificationReport,
)
from app.models.schemas import AgentName, EventStatus, ProgressEvent

logger = logging.getLogger(__name__)

# Completed papers are written here so they survive a server restart (e.g. the
# uvicorn --reload watcher) — the in-memory store alone would lose them.
_CACHE_DIR = Path(__file__).resolve().parents[2] / ".paper_cache"


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
        job = self._jobs.get(job_id)
        if job is not None:
            return job
        # Not in memory (e.g. after a restart) — try the on-disk cache.
        return self._load(job_id)

    def _persist(self, job: PaperJob) -> None:
        if job.result is None:
            return
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            (_CACHE_DIR / f"{job.id}.json").write_text(
                job.result.model_dump_json(), encoding="utf-8"
            )
        except Exception:  # persistence is best-effort
            logger.exception("Failed to persist paper %s.", job.id)

    def _load(self, job_id: str) -> Optional[PaperJob]:
        path = _CACHE_DIR / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            result = PaperResult.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load cached paper %s.", job_id)
            return None
        job = PaperJob(
            id=job_id,
            topic=result.topic,
            details=result.details,
            authors=[a.model_dump() for a in result.authors],
            status=result.status,
            result=result,
            finished=True,
        )
        self._jobs[job_id] = job  # re-cache in memory
        return job

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
            # The paper graph has ~11 nodes plus the bounded Critic->Searcher
            # re-search loop, which can exceed LangGraph's default step limit (25).
            settings = get_settings()
            recursion_limit = 20 + settings.max_research_rounds * 4 + 10
            final = await asyncio.to_thread(
                paper_graph.invoke, state, {"recursion_limit": recursion_limit}
            )
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
            self._persist(job)  # survive restarts
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
    tables = [PaperTable(**t) for t in state.get("tables", [])]
    figures = [PaperFigure(**f) for f in state.get("figures", [])]
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
        tables=tables,
        figures=figures,
        references=references,
        originality=originality,
        verification=verification,
        paper_markdown=state.get("paper_markdown", ""),
        rounds_used=min(state.get("round_count", 0), settings.max_research_rounds + 1),
    )


paper_job_manager = PaperJobManager()
