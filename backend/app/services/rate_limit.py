"""Client-side rate limiting + 429-aware retry for Groq calls.

The free Groq tier enforces per-minute (RPM/TPM) *and* per-day (TPD) limits. We:
  - throttle calls to a minimum interval (spreads bursts under the per-minute cap),
  - on a 429, parse Groq's "try again in Xs" hint and back off, retrying;
  - if the suggested wait is huge (a per-*day* exhaustion), stop with a clear
    error instead of blocking the request for tens of minutes.
"""

from __future__ import annotations

import logging
import re
import threading
import time

from app.config import get_settings

logger = logging.getLogger(__name__)

_RETRY_HINT = re.compile(r"try again in ([\d.]+)\s*([ms])", re.IGNORECASE)


class RateLimitExceeded(RuntimeError):
    """Raised when retries are exhausted or a daily limit is hit."""


class _MinIntervalLimiter:
    """Serialises calls so consecutive requests are spaced by ``min_interval``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self, min_interval: float) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < min_interval:
                time.sleep(min_interval - delta)
            self._last = time.monotonic()


_limiter = _MinIntervalLimiter()


def _parse_retry_seconds(message: str) -> float | None:
    m = _RETRY_HINT.search(message)
    if not m:
        return None
    value = float(m.group(1))
    return value * 60.0 if m.group(2).lower() == "m" else value


def invoke_with_retry(llm, messages):
    """Invoke ``llm`` with throttling + 429 backoff. Returns the model message."""
    settings = get_settings()
    attempts = settings.llm_max_retries + 1

    for attempt in range(attempts):
        _limiter.wait(settings.llm_min_interval_seconds)
        try:
            return llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - inspect message for rate limiting
            msg = str(exc)
            is_429 = "429" in msg or "rate_limit" in msg.lower() or "rate limit" in msg.lower()
            if not is_429 or attempt == attempts - 1:
                raise

            hinted = _parse_retry_seconds(msg)
            wait = hinted if hinted is not None else min(2.0 * (2 ** attempt), 30.0)
            if wait > settings.llm_max_backoff_seconds:
                # A large wait means the daily token cap is exhausted; don't
                # block the whole pipeline — surface it so callers degrade.
                raise RateLimitExceeded(
                    f"Groq rate limit; suggested wait {wait:.0f}s exceeds cap "
                    f"({settings.llm_max_backoff_seconds:.0f}s). Likely the daily "
                    "token limit — wait for reset or use a paid tier."
                ) from exc

            logger.warning(
                "Rate limited (attempt %d/%d); backing off %.1fs.", attempt + 1, attempts, wait
            )
            time.sleep(wait + 0.5)

    raise RateLimitExceeded("Exhausted retries due to rate limiting.")
