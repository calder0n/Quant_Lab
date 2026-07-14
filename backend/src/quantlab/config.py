"""Application configuration.

A single, typed source of truth loaded from environment variables (prefix ``QL_``)
or an optional ``.env`` file. No module-level singletons: callers instantiate
``Settings`` explicitly (normally once, inside the composition root).
"""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]
BrokerEnvironment = Literal["practice", "live"]


class Settings(BaseSettings):
    """Runtime configuration for every QuantLab process (API, workers, CLI)."""

    model_config = SettingsConfigDict(
        env_prefix="QL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "QuantLab"
    environment: Environment = "dev"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "quantlab"
    postgres_password: str = "quantlab"
    postgres_db: str = "quantlab"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # Health checks
    health_check_timeout_seconds: float = 2.0

    # Market data storage
    data_dir: Path = Path("/data")
    history_start: date = date(2020, 1, 1)

    # OANDA
    oanda_api_token: str = ""
    oanda_environment: BrokerEnvironment = "practice"
    oanda_account_id: str = ""

    @property
    def postgres_dsn(self) -> str:
        """Async SQLAlchemy DSN for the application engine."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Connection URL for the Redis cache/queue."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
