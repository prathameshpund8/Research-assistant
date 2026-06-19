"""Groq LLM client factory.

We use ``langchain-groq``'s :class:`ChatGroq` so the model wires cleanly into
LangGraph nodes. The API key is read from :class:`Settings` only — never
hardcoded. If no key is configured the factory raises a clear error so the
caller can decide how to degrade.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache

import httpx
from langchain_groq import ChatGroq

from app.config import get_settings
from app.tls import configure_tls

logger = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM is requested but no Groq API key is configured."""


# --- Multi-key rotation ----------------------------------------------------
# A single global "active key" index, shared across every model. The daily
# token limit is per-account, so when one key is exhausted we advance this index
# and all models switch to the next key together.
_key_lock = threading.Lock()
_active_key_index = 0


def active_key_index() -> int:
    return _active_key_index


def rotate_key() -> bool:
    """Advance to the next configured key. Returns False if none remain."""
    global _active_key_index
    with _key_lock:
        keys = get_settings().groq_api_keys
        if _active_key_index + 1 < len(keys):
            _active_key_index += 1
            logger.warning(
                "Rotating to Groq key #%d of %d (previous key hit its limit).",
                _active_key_index + 1,
                len(keys),
            )
            return True
        return False


def key_count() -> int:
    return len(get_settings().groq_api_keys)


class _RotatingLLM:
    """A model wrapper that builds one ChatGroq client per API key on demand.

    Agents call ``llm.invoke(messages)`` unchanged. Throttling, 429 backoff, and
    key rotation are applied by ``invoke_with_retry``. ``current_client()``
    returns the client bound to the currently-active key.
    """

    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._clients: dict[int, ChatGroq] = {}

    def current_client(self) -> ChatGroq:
        idx = active_key_index()
        if idx not in self._clients:
            keys = get_settings().groq_api_keys
            self._clients[idx] = _build_client(
                self.model, self.temperature, self.max_tokens, keys[idx]
            )
        return self._clients[idx]

    @property
    def model_name(self) -> str:
        return self.model

    def invoke(self, messages, **_kw):
        from app.services.rate_limit import invoke_with_retry

        return invoke_with_retry(self, messages)


@lru_cache
def get_llm(temperature: float = 0.2) -> _RotatingLLM:
    """Primary model (section writing, outlining) with key rotation."""
    _require_key()
    return _RotatingLLM(get_settings().groq_model, temperature, max_tokens=3072)


@lru_cache
def get_fast_llm(temperature: float = 0.2) -> _RotatingLLM:
    """Cheaper/faster model for high-volume agents (summarize, paraphrase)."""
    _require_key()
    return _RotatingLLM(get_settings().groq_fast_model, temperature, max_tokens=1536)


def _require_key() -> None:
    if not get_settings().has_groq:
        raise LLMConfigurationError(
            "No GROQ_API_KEY set. Add it to your environment or .env file."
        )


def _build_client(model: str, temperature: float, max_tokens: int, api_key: str) -> ChatGroq:
    settings = get_settings()
    # Ensure HTTPS verification trusts the corporate/OS CA before any API call.
    configure_tls()

    # Last-resort insecure mode: hand ChatGroq httpx clients with verification
    # off. The secure default (verify_ssl=True) relies on truststore instead.
    extra: dict = {}
    if not settings.verify_ssl:
        extra["http_client"] = httpx.Client(verify=False, timeout=60)
        extra["http_async_client"] = httpx.AsyncClient(verify=False, timeout=60)

    base_url = _normalize_groq_base_url(settings.groq_base_url)

    logger.info("Initialising ChatGroq model=%s base_url=%s", model, base_url)
    return ChatGroq(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=0,  # our invoke_with_retry handles backoff + rotation
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
        "fast_model": settings.groq_fast_model,
        "base_url": settings.groq_base_url,
        "keys_configured": len(settings.groq_api_keys),
        "active_key": active_key_index() + 1 if settings.has_groq else 0,
    }
