"""Groq LLM client factory.

We use ``langchain-groq``'s :class:`ChatGroq` so the model wires cleanly into
LangGraph nodes. The API key is read from :class:`Settings` only — never
hardcoded. If no key is configured the factory raises a clear error so the
caller can decide how to degrade.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from langchain_groq import ChatGroq

from app.config import get_settings
from app.tls import configure_tls

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
    # Ensure HTTPS verification trusts the corporate/OS CA before any API call.
    configure_tls()

    if not settings.has_groq:
        raise LLMConfigurationError(
            "GROQ_API_KEY is not set. Add it to your environment or .env file."
        )

    # Last-resort insecure mode: hand ChatGroq httpx clients with verification
    # off. The secure default (verify_ssl=True) relies on truststore instead.
    extra: dict = {}
    if not settings.verify_ssl:
        extra["http_client"] = httpx.Client(verify=False, timeout=60)
        extra["http_async_client"] = httpx.AsyncClient(verify=False, timeout=60)

    base_url = _normalize_groq_base_url(settings.groq_base_url)

    logger.info("Initialising ChatGroq model=%s base_url=%s", settings.groq_model, base_url)
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=base_url,
        temperature=temperature,
        # Keep responses bounded so hierarchical summaries stay within context.
        max_tokens=2048,
        timeout=60,
        max_retries=2,
        **extra,
    )


def _normalize_groq_base_url(url: str) -> str:
    """Return the host base Groq's SDK expects (without the ``/openai/v1`` path).

    The native Groq client appends ``/openai/v1/chat/completions`` itself, so a
    configured value of ``https://api.groq.com/openai/v1`` would double the path
    (``/openai/v1/openai/v1/...`` → 404). We accept either form and strip a
    trailing ``/openai/v1`` so both work.
    """
    base = url.strip().rstrip("/")
    if base.endswith("/openai/v1"):
        base = base[: -len("/openai/v1")]
    return base or "https://api.groq.com"


def llm_health() -> dict[str, object]:
    """Lightweight readiness info for the /health endpoint (no network call)."""
    settings = get_settings()
    return {
        "configured": settings.has_groq,
        "model": settings.groq_model,
        "base_url": settings.groq_base_url,
    }
