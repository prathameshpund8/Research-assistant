"""IEEE paper API routes.

  POST /api/paper                -> start a paper job, returns {paper_id}
  GET  /api/paper/{id}/stream    -> SSE stream of per-agent progress
  GET  /api/paper/{id}           -> structured paper (preview + reports)
  GET  /api/paper/{id}/docx      -> download IEEE-formatted .docx
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from app.models.paper_schemas import PaperAccepted, PaperRequest, PaperResult
from app.services.docx_export import build_paper_docx
from app.services.paper_jobs import paper_job_manager

logger = logging.getLogger(__name__)
router = APIRouter()

_HEARTBEAT = 15.0


@router.post("/paper", response_model=PaperAccepted, status_code=202)
async def start_paper(req: PaperRequest) -> PaperAccepted:
    authors = [a.model_dump() for a in req.authors] or [{}]
    job = paper_job_manager.start(req.topic.strip(), req.details.strip(), authors)
    logger.info("Started paper job %s for topic %r", job.id, req.topic)
    return PaperAccepted(paper_id=job.id)


@router.get("/paper/{paper_id}/stream")
async def stream_paper(paper_id: str) -> EventSourceResponse:
    job = paper_job_manager.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="paper_id not found")

    async def event_generator():
        cursor = 0
        while True:
            while cursor < len(job.events):
                event = job.events[cursor]
                cursor += 1
                yield {"event": "progress", "data": event.model_dump_json()}
            if job.finished and cursor >= len(job.events):
                yield {"event": "done", "data": "{}"}
                break
            sig = job.signal()
            try:
                await asyncio.wait_for(sig.wait(), timeout=_HEARTBEAT)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}
            finally:
                if cursor >= len(job.events):
                    sig.clear()

    return EventSourceResponse(event_generator())


@router.get("/paper/{paper_id}", response_model=PaperResult)
async def get_paper(paper_id: str) -> PaperResult:
    job = paper_job_manager.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="paper_id not found")
    if job.result is not None:
        return job.result
    return PaperResult(paper_id=job.id, topic=job.topic, details=job.details, status=job.status)


@router.get("/paper/{paper_id}/docx")
async def download_paper_docx(paper_id: str) -> Response:
    job = paper_job_manager.get(paper_id)
    if job is None or job.result is None or job.result.status != "completed":
        raise HTTPException(status_code=404, detail="paper not ready")

    data = build_paper_docx(job.result)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (job.result.title or job.topic)).strip("-")[:60] or "paper"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{slug}.docx"'},
    )
