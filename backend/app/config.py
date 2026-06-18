"""Application configuration.

All settings are loaded from environment variables (and an optional local
`.env` file) via pydantic-settings. Secrets such as ``GROQ_API_KEY`` are NEVER
hardcoded — they must be supplied through the environment.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, sourced from env / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Groq -------------------------------------------------------------
    groq_api_key: str = Field(default="", description="Groq API key (required for live LLM).")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model id.")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="OpenAI-compatible Groq base URL.",
    )

    # --- Tavily -----------------------------------------------------------
    tavily_api_key: str = Field(default="", description="Tavily search key (optional).")

    # --- Agent behaviour --------------------------------------------------
    max_research_rounds: int = Field(default=2, ge=0, le=5)
    search_results_per_query: int = Field(default=4, ge=1, le=10)

    # --- CORS -------------------------------------------------------------
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:4200", "http://127.0.0.1:4200"]
    )

    # --- Server -----------------------------------------------------------
    log_level: str = Field(default="INFO")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv_origins(cls, value: object) -> object:
        """Allow CORS_ORIGINS to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one read of the environment)."""
    return Settings()
