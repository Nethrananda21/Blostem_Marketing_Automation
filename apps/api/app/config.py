from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Blostem API"
    env: Literal["development", "test", "production"] = "development"
    api_root_path: str = Field(default="/api", alias="API_ROOT_PATH")
    app_public_origin: str = Field(default="http://localhost:3000", alias="APP_PUBLIC_ORIGIN")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./apps/api/dev.db",
        alias="DATABASE_URL",
    )
    clickhouse_url: str = Field(default="http://localhost:8123", alias="CLICKHOUSE_URL")
    clickhouse_database: str = Field(default="default", alias="CLICKHOUSE_DATABASE")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    redpanda_brokers: str = Field(default="localhost:19092", alias="REDPANDA_BROKERS")
    object_storage_endpoint: str = Field(
        default="http://localhost:9000",
        alias="OBJECT_STORAGE_ENDPOINT",
    )
    object_storage_bucket: str = Field(default="blostem-raw", alias="OBJECT_STORAGE_BUCKET")
    object_storage_access_key: str = Field(
        default="minioadmin",
        alias="OBJECT_STORAGE_ACCESS_KEY",
    )
    object_storage_secret_key: str = Field(
        default="minioadmin",
        alias="OBJECT_STORAGE_SECRET_KEY",
    )
    temporal_server_url: str = Field(default="localhost:7233", alias="TEMPORAL_SERVER_URL")
    temporal_namespace: str = Field(default="default", alias="TEMPORAL_NAMESPACE")
    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        alias="NVIDIA_BASE_URL",
    )
    nvidia_model_kimi: str = Field(
        default="moonshotai/kimi-k2.5",
        alias="NVIDIA_MODEL_KIMI",
    )
    nvidia_kimi_fallback_models: str = Field(
        default="moonshotai/kimi-k2-thinking,moonshotai/kimi-k2-instruct-0905,moonshotai/kimi-k2-instruct",
        alias="NVIDIA_KIMI_FALLBACK_MODELS",
    )
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_model_gemma: str = Field(
        default="google/gemma-4-31b-it",
        alias="OPENROUTER_MODEL_GEMMA",
    )
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")
    discovery_scheduler_enabled: bool = Field(default=False, alias="DISCOVERY_SCHEDULER_ENABLED")
    automation_poll_seconds: int = Field(default=300, alias="AUTOMATION_POLL_SECONDS")
    live_search_provider: Literal["auto", "tavily", "duckduckgo"] = Field(
        default="auto",
        alias="LIVE_SEARCH_PROVIDER",
    )
    live_search_max_results: int = Field(default=5, alias="LIVE_SEARCH_MAX_RESULTS")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")

    # ── Email delivery ────────────────────────────────────────────────────────
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    # In demo/test mode every outbound email is redirected here (no real pros contacted)
    demo_email_override: str = Field(
        default="nethranandareddy9@gmail.com",
        alias="DEMO_EMAIL_OVERRIDE",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
