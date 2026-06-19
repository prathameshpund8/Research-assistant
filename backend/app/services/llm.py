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


class _RetryingLLM:
    """Wraps a ChatGroq so every ``.invoke`` is throttled and 429-retried.

    Agents call ``llm.invoke(messages)`` unchanged; rate limiting is applied
    transparently. Other attributes pass through to the wrapped client.
    """

    def __init__(self, inner: ChatGroq) -> None:
        self._inner = inner

    def invoke(self, messages, **_kw):
        from app.services.rate_limit import invoke_with_retry

        return invoke_with_retry(self._inner, messages)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@lru_cache
def get_llm(temperature: float = 0.2) -> _RetryingLLM:
    """Build (and cache) the primary rate-limited ChatGroq client."""
    return _build(get_settings().groq_model, temperature, max_tokens=3072)


@lru_cache
def get_fast_llm(temperature: float = 0.2) -> _RetryingLLM:
    """Cheaper/faster model for high-volume agents (summarize, paraphrase)."""
    return _build(get_settings().groq_fast_model, temperature, max_tokens=1536)


def _build(model: str, temperature: float, max_tokens: int) -> _RetryingLLM:
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

    logger.info("Initialising ChatGroq model=%s base_url=%s", model, base_url)
    client = ChatGroq(
        api_key=settings.groq_api_key,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=0,  # our invoke_with_retry handles backoff
        **extra,
    )
    return _RetryingLLM(client)


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
