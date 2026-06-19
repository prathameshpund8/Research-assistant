"""FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload

Phase 1 exposes configuration loading, the Groq LLM client factory, and a
health check. Later phases mount the /api/research routes.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.models.schemas import HealthResponse
from app.services.llm import llm_health
from app.services.search import get_search_service
from app.tls import configure_tls

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger("research_assistant")

# Trust the OS/corporate CA store for all outbound HTTPS (Groq, Tavily) before
# any client is created. Without this, HTTPS-inspection proxies break TLS.
configure_tls()

app = FastAPI(
    title="Autonomous Research Assistant",
    version=__version__,
    description="Multi-agent research pipeline (Planner→Searcher→Summarizer→Critic→Writer).",
)

# CORS so the Angular dev server (http://localhost:4200) can call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"service": "autonomous-research-assistant", "version": __version__}


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Readiness probe — reports LLM + search configuration (no network calls)."""
    return HealthResponse(
        status="ok",
        version=__version__,
        llm=llm_health(),
        search=get_search_service().health(),
    )


# --- Research + paper API routes -------------------------------------------
from app.api.routes import router as research_router  # noqa: E402
from app.api.paper_routes import router as paper_router  # noqa: E402

app.include_router(research_router, prefix="/api", tags=["research"])
app.include_router(paper_router, prefix="/api", tags=["paper"])
logger.info("Research + paper routes mounted at /api")
