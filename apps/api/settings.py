"""
apps/api/settings.py

Application settings loaded from environment variables via pydantic-settings.

SECURITY: No credentials have default values that would be safe in production.
          Settings are validated at startup — the application will refuse to
          start if required settings are missing or invalid.
          Secrets are masked from string representations.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

    All values are sourced from environment variables.
    An optional .env file is loaded for local development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- Application -----
    app_env: str = Field(default="development", description="Environment: 'development', 'test', 'production'")
    app_debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    log_json: Optional[bool] = Field(default=None, description="Use JSON logs; defaults to true in production")

    # ----- API -----
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    admin_api_key: Optional[str] = Field(default=None, description="Secret token for administrative endpoints")

    # ----- Database -----
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="financial_agent_lab")
    db_user: str = Field(default="fal_user")
    db_password: str = Field(default="")

    # ----- Razorpay Gateway -----
    razorpay_webhook_secret: str = Field(default="test_webhook_secret_local")

    # ----- Block 4 AI Recovery Decision Provider -----
    ai_provider: str = Field(default="mock", description="AI provider type: 'mock', 'gemini', 'openai', 'ollama'")
    ai_model: str = Field(default="gemini-2.5-flash", description="Model name to use (e.g. 'gemini-2.5-flash', 'gpt-4o-mini')")
    ai_api_key: Optional[str] = Field(default=None, description="API key for live LLM providers")
    ai_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta", description="API base URL")
    ai_timeout_seconds: float = Field(default=15.0, description="HTTP timeout for AI inference calls")
    ai_cost_per_million_input_tokens_usd: float = Field(default=0.075, description="Input token pricing ($/M)")
    ai_cost_per_million_output_tokens_usd: float = Field(default=0.30, description="Output token pricing ($/M)")
    usd_to_inr_rate: float = Field(default=85.0, description="USD to INR exchange rate for inference cost estimation")

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def effective_log_json(self) -> bool:
        """Production emits JSON logs unless explicitly configured otherwise."""
        return self.app_env == "production" if self.log_json is None else self.log_json

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid LOG_LEVEL '{v}'. Must be one of {valid_levels}")
        return upper_v

    @model_validator(mode="after")
    def _validate_env(self) -> Settings:
        if self.app_env == "production":
            if not self.db_password:
                raise ValueError("DB_PASSWORD must be set in production.")
            if not self.razorpay_webhook_secret or self.razorpay_webhook_secret == "test_webhook_secret_local":
                raise ValueError("A secure RAZORPAY_WEBHOOK_SECRET must be set in production.")
            if not self.admin_api_key:
                raise ValueError("ADMIN_API_KEY must be set in production.")
        return self

    def sanitized_dict(self) -> dict[str, Any]:
        """Return configuration dictionary with all secrets securely masked."""
        raw = self.model_dump()
        secret_keys = {"db_password", "razorpay_webhook_secret", "ai_api_key", "admin_api_key"}
        for k in secret_keys:
            if k in raw and raw[k]:
                raw[k] = "***REDACTED***"
        return raw

    def __repr__(self) -> str:
        return f"Settings({self.sanitized_dict()})"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
