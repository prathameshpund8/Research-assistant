"""Research API routes.

  POST /api/research                 -> start a job, returns {research_id}
  GET  /api/research/{id}/stream     -> SSE stream of per-agent progress events
  GET  /api/research/{id}            -> final result (Markdown + structured JSON)
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import ResearchAccepted, ResearchRequest, ResearchResult
from app.services.jobs import job_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# Heartbeat interval (seconds) so proxies don't drop an idle SSE connection.
_HEARTBEAT = 15.0


@router.post("/research", response_model=ResearchAccepted, status_code=202)
async def start_research(req: ResearchRequest) -> ResearchAccepted:
    """Kick off a research run in the background."""
    job = job_manager.start(req.query.strip())
    logger.info("Started research job %s for query %r", job.id, req.query)
    return ResearchAccepted(research_id=job.id)


@router.get("/research/{research_id}/stream")
async def stream_research(research_id: str) -> EventSourceResponse:
    """Stream agent progress events as Server-Sent Events.

    Replays any events already buffered (so a late subscriber doesn't miss the
    start), then streams live until the job finishes.
    """
    job = job_manager.get(research_id)
    if job is None:
        raise HTTPException(status_code=404, detail="research_id not found")

    async def event_generator():
        cursor = 0
        while True:
            # Drain everything buffered since the last cursor position.
            while cursor < len(job.events):
                event = job.events[cursor]
                cursor += 1
                yield {
                    "event": "progress",
                    "data": event.model_dump_json(),
                }

            if job.finished and cursor >= len(job.events):
                yield {"event": "done", "data": "{}"}
                break

            # Wait for new events or send a heartbeat to keep the pipe open.
            sig = job.signal()
            try:
                await asyncio.wait_for(sig.wait(), timeout=_HEARTBEAT)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}
            finally:
                # Re-arm only if we've consumed everything; otherwise loop drains.
                if cursor >= len(job.events):
                    sig.clear()

    return EventSourceResponse(event_generator())


@router.get("/research/{research_id}", response_model=ResearchResult)
async def get_research(research_id: str) -> ResearchResult:
    """Return the final result; 202-style placeholder while still running."""
    job = job_manager.get(research_id)
    if job is None:
        raise HTTPException(status_code=404, detail="research_id not found")
    if job.result is not None:
        return job.result
    # Still running — return a lightweight in-progress view.
    return ResearchResult(research_id=job.id, query=job.query, status=job.status)
