"""Application configuration.

All settings are loaded from environment variables (and an optional local
`.env` file) via pydantic-settings. Secrets such as ``GROQ_API_KEY`` are NEVER
hardcoded — they must be supplied through the environment.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, sourced from env / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Groq -------------------------------------------------------------
    # Up to three keys. Put keys from DIFFERENT Groq accounts here — the daily
    # token limit is per-account, so separate accounts multiply your budget.
    # When one key hits its daily cap, the app rotates to the next.
    groq_api_key: str = Field(default="", description="Groq API key #1 (required for live LLM).")
    groq_api_key_2: str = Field(default="", description="Groq API key #2 (optional, for rotation).")
    groq_api_key_3: str = Field(default="", description="Groq API key #3 (optional, for rotation).")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model id.")
    # Cheaper/faster model for high-volume agents (summarize, paraphrase) to
    # conserve the daily token budget.
    groq_fast_model: str = Field(default="llama-3.1-8b-instant")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="OpenAI-compatible Groq base URL.",
    )

    # --- Rate limiting / retry (avoids HTTP 429 storms on free tier) -------
    # Minimum seconds between LLM calls (throttle), and how long we'll back off
    # on a 429 before giving up. Generation may be slow but won't fail-fast.
    llm_min_interval_seconds: float = Field(default=2.0, ge=0.0, le=30.0)
    llm_max_retries: int = Field(default=5, ge=0, le=10)
    llm_max_backoff_seconds: float = Field(default=90.0, ge=5.0, le=600.0)

    # --- Tavily -----------------------------------------------------------
    tavily_api_key: str = Field(default="", description="Tavily search key (optional).")

    # --- Agent behaviour --------------------------------------------------
    max_research_rounds: int = Field(default=2, ge=0, le=5)
    search_results_per_query: int = Field(default=4, ge=1, le=10)

    # --- CORS -------------------------------------------------------------
    # NoDecode tells pydantic-settings NOT to JSON-decode this env value, so a
    # plain comma-separated string (CORS_ORIGINS=a,b) reaches the validator
    # below instead of crashing the JSON parser.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4200", "http://127.0.0.1:4200"]
    )

    # --- TLS / networking -------------------------------------------------
    # On corporate networks that do HTTPS inspection, the TLS chain is re-signed
    # with an internal root CA. With verify_ssl=True (default) we trust the OS
    # certificate store (which already has that CA) via `truststore`. Set to
    # False only as a last resort to disable verification entirely (insecure).
    verify_ssl: bool = Field(default=True)

    # --- Server -----------------------------------------------------------
    log_level: str = Field(default="INFO")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv_origins(cls, value: object) -> object:
        """Accept CORS_ORIGINS as CSV ("a,b") or a JSON array ('["a","b"]')."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @property
    def groq_api_keys(self) -> list[str]:
        """All configured Groq keys, in rotation order (deduped, non-empty)."""
        seen: list[str] = []
        for key in (self.groq_api_key, self.groq_api_key_2, self.groq_api_key_3):
            k = key.strip()
            if k and k not in seen:
                seen.append(k)
        return seen

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_keys)

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one read of the environment)."""
    return Settings()
