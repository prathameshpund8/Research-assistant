"""Groq LLM client factory.

We use ``langchain-groq``'s :class:`ChatGroq` so the model wires cleanly into
LangGraph nodes. The API key is read from :class:`Settings` only — never
hardcoded. If no key is configured the factory raises a clear error so the
caller can decide how to degrade.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_groq import ChatGroq

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM is requested but no Groq API key is configured."""


@lru_cache
def get_llm(temperature: float = 0.2) -> ChatGroq:
    """Build (and cache) a ChatGroq client.

    Args:
        temperature: Sampling temperature. Lower is more deterministic, which
            suits planning / fact-extraction; the Writer may use a touch more.

    Raises:
        LLMConfigurationError: if ``GROQ_API_KEY`` is missing.
    """
    settings = get_settings()
    if not settings.has_groq:
        raise LLMConfigurationError(
            "GROQ_API_KEY is not set. Add it to your environment or .env file."
        )

    logger.info("Initialising ChatGroq model=%s", settings.groq_model)
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        temperature=temperature,
        # Keep responses bounded so hierarchical summaries stay within context.
        max_tokens=2048,
        timeout=60,
        max_retries=2,
    )


def llm_health() -> dict[str, object]:
    """Lightweight readiness info for the /health endpoint (no network call)."""
    settings = get_settings()
    return {
        "configured": settings.has_groq,
        "model": settings.groq_model,
        "base_url": settings.groq_base_url,
    }
