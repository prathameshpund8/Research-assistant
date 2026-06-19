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
    """Invoke ``llm`` with throttling, 429 backoff, and multi-key rotation.

    - Per-minute (TPM/RPM) limits ⇒ short suggested wait ⇒ back off and retry.
    - Per-day (TPD) limits ⇒ huge suggested wait ⇒ rotate to the next API key
      (if configured) and retry immediately; only give up once every key is
      exhausted.

    ``llm`` may be a plain client (with ``.invoke``) or a rotating wrapper
    (with ``.current_client()``); both are supported.
    """
    from app.services.llm import rotate_key  # local import avoids a cycle

    settings = get_settings()
    max_backoff_retries = settings.llm_max_retries

    def _call():
        target = getattr(llm, "current_client", None)
        return (target() if callable(target) else llm).invoke(messages)

    backoff_attempt = 0
    while True:
        _limiter.wait(settings.llm_min_interval_seconds)
        try:
            return _call()
        except Exception as exc:  # noqa: BLE001 - inspect message for rate limiting
            msg = str(exc)
            is_429 = "429" in msg or "rate_limit" in msg.lower() or "rate limit" in msg.lower()
            if not is_429:
                raise

            hinted = _parse_retry_seconds(msg)
            wait = hinted if hinted is not None else min(2.0 * (2 ** backoff_attempt), 30.0)

            if wait > settings.llm_max_backoff_seconds:
                # Daily cap on the current key — switch keys and retry at once.
                if rotate_key():
                    continue
                raise RateLimitExceeded(
                    "All configured Groq keys are rate-limited (daily token cap). "
                    "Add more keys from separate accounts, wait for reset, or use a "
                    "paid tier."
                ) from exc

            # Per-minute limit — bounded exponential backoff on the same key.
            if backoff_attempt >= max_backoff_retries:
                raise RateLimitExceeded("Exhausted retries due to per-minute rate limiting.") from exc
            logger.warning(
                "Rate limited (attempt %d/%d); backing off %.1fs.",
                backoff_attempt + 1,
                max_backoff_retries,
                wait,
            )
            time.sleep(wait + 0.5)
            backoff_attempt += 1
