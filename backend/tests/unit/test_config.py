"""Tests for quantlab.config."""

import pytest

from quantlab.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "QuantLab"
    assert settings.environment == "dev"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.debug is False


def test_postgres_dsn_is_built_from_parts() -> None:
    settings = Settings(
        _env_file=None,
        postgres_host="db.local",
        postgres_port=5555,
        postgres_user="alice",
        postgres_password="secret",
        postgres_db="lab",
    )
    assert settings.postgres_dsn == "postgresql+asyncpg://alice:secret@db.local:5555/lab"


def test_redis_url_is_built_from_parts() -> None:
    settings = Settings(_env_file=None, redis_host="cache.local", redis_port=7000, redis_db=3)
    assert settings.redis_url == "redis://cache.local:7000/3"


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QL_POSTGRES_HOST", "envhost")
    monkeypatch.setenv("QL_ENVIRONMENT", "prod")
    monkeypatch.setenv("QL_DEBUG", "true")
    settings = Settings(_env_file=None)
    assert settings.postgres_host == "envhost"
    assert settings.environment == "prod"
    assert settings.debug is True
