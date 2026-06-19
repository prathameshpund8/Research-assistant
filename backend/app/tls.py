"""Corporate-TLS support.

On networks that perform HTTPS inspection (corporate proxies / firewalls), the
TLS chain presented to clients is re-signed with an *internal* root CA. Browsers
trust it because it's installed in the OS certificate store, but Python's bundled
``certifi`` store does not — so outbound HTTPS calls fail with::

    [SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain

We fix this by injecting the OS trust store (which already trusts the corporate
CA) via the ``truststore`` package. This patches the stdlib ``ssl`` module, so it
covers every HTTPS client we use (Groq via httpx, Tavily, etc.).

Controlled by the ``VERIFY_SSL`` setting:
- True  (default): use the OS certificate store.
- False (insecure): skip injection; callers disable verification explicitly.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_configured = False


def configure_tls() -> None:
    """Enable OS-trust-store verification once per process (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True

    # Imported here to avoid a circular import at module load time.
    from app.config import get_settings

    settings = get_settings()
    if not settings.verify_ssl:
        logger.warning(
            "VERIFY_SSL=false — TLS certificate verification is DISABLED. "
            "This is insecure; prefer trusting your corporate CA instead."
        )
        return

    try:
        import truststore

        truststore.inject_into_ssl()
        logger.info("TLS: verifying HTTPS against the OS certificate store (truststore).")
    except Exception as exc:  # truststore missing or platform issue
        logger.warning(
            "TLS: could not enable OS trust store (%s); falling back to certifi. "
            "If you see CERTIFICATE_VERIFY_FAILED, install truststore or set a CA bundle.",
            exc,
        )
