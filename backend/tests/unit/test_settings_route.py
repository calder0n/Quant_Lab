"""Tests for the broker settings API routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from quantlab.application.ports import BrokerSettingsRepository
from quantlab.config import Settings
from quantlab.domain.broker import OANDA, BrokerCredentials
from quantlab.infrastructure.brokers.oanda.verification import VerificationResult
from quantlab.interfaces.api.app import create_app
from quantlab.interfaces.api.routes import settings as settings_routes


class InMemoryBrokerRepo(BrokerSettingsRepository):
    def __init__(self, store: dict[str, BrokerCredentials]) -> None:
        self._store = store

    async def get(self, broker: str) -> BrokerCredentials | None:
        return self._store.get(broker)

    async def upsert(self, credentials: BrokerCredentials) -> BrokerCredentials:
        credentials.updated_at = datetime.now(UTC)
        self._store[credentials.broker] = credentials
        return credentials

    async def delete(self, broker: str) -> None:
        self._store.pop(broker, None)


class SettingsStubContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store: dict[str, BrokerCredentials] = {}

    @asynccontextmanager
    async def broker_settings_repository(self) -> AsyncIterator[BrokerSettingsRepository]:
        yield InMemoryBrokerRepo(self.store)


def build_client(app: FastAPI, container: SettingsStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def make_container(oanda_env_token: str = "") -> tuple[FastAPI, SettingsStubContainer]:
    settings = Settings(_env_file=None, environment="test", oanda_api_token=oanda_env_token)
    return create_app(settings), SettingsStubContainer(settings)


async def test_get_reports_unconfigured_state() -> None:
    app, container = make_container()
    async with build_client(app, container) as client:
        response = await client.get("/api/v1/settings/broker")
    body = response.json()
    assert response.status_code == 200
    assert body["configured"] is False
    assert body["source"] == "none"
    assert body["token_preview"] is None


async def test_get_falls_back_to_environment_credentials() -> None:
    app, container = make_container(oanda_env_token="env-token-12345")
    async with build_client(app, container) as client:
        response = await client.get("/api/v1/settings/broker")
    body = response.json()
    assert body["configured"] is True
    assert body["source"] == "environment"
    assert body["token_preview"] == "····2345"
    assert "env-token" not in str(body)  # full token never leaves the backend


async def test_put_stores_credentials_and_masks_token() -> None:
    app, container = make_container()
    async with build_client(app, container) as client:
        response = await client.put(
            "/api/v1/settings/broker",
            json={
                "api_token": "portal-token-9876",
                "account_id": "001-004-111-001",
                "environment": "practice",
            },
        )
        body = response.json()
        assert response.status_code == 200
        assert body["configured"] is True
        assert body["source"] == "database"
        assert body["token_preview"] == "····9876"
        assert body["account_id"] == "001-004-111-001"

        fetched = (await client.get("/api/v1/settings/broker")).json()
    assert fetched["source"] == "database"
    assert container.store[OANDA].api_token == "portal-token-9876"


async def test_partial_put_keeps_existing_token() -> None:
    app, container = make_container()
    container.store[OANDA] = BrokerCredentials(api_token="portal-token-9876")
    async with build_client(app, container) as client:
        response = await client.put(
            "/api/v1/settings/broker", json={"account_id": "001-9", "environment": "live"}
        )
    body = response.json()
    assert body["token_preview"] == "····9876"
    assert body["environment"] == "live"
    assert container.store[OANDA].api_token == "portal-token-9876"


async def test_put_rejects_too_short_token() -> None:
    app, container = make_container()
    async with build_client(app, container) as client:
        response = await client.put("/api/v1/settings/broker", json={"api_token": "abc"})
    assert response.status_code == 422


async def test_delete_removes_portal_credentials() -> None:
    app, container = make_container(oanda_env_token="env-token-12345")
    container.store[OANDA] = BrokerCredentials(api_token="portal-token-9876")
    async with build_client(app, container) as client:
        response = await client.delete("/api/v1/settings/broker")
    body = response.json()
    assert OANDA not in container.store
    assert body["source"] == "environment"  # env fallback becomes active again
    assert body["token_preview"] == "····2345"


async def test_connection_test_uses_resolved_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, container = make_container()
    container.store[OANDA] = BrokerCredentials(api_token="portal-token-9876", account_id="001-1")
    received: list[BrokerCredentials] = []

    async def fake_verify(
        credentials: BrokerCredentials, http: object = None
    ) -> VerificationResult:
        received.append(credentials)
        return VerificationResult(ok=True, detail="Connected", accounts=["001-1"])

    monkeypatch.setattr(settings_routes, "verify_credentials", fake_verify)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/settings/broker/test")
    body = response.json()
    assert body["ok"] is True
    assert body["accounts"] == ["001-1"]
    assert received[0].api_token == "portal-token-9876"


async def test_connection_test_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    app, container = make_container()

    async def fake_verify(
        credentials: BrokerCredentials, http: object = None
    ) -> VerificationResult:
        return VerificationResult(ok=False, detail="No API token configured.")

    monkeypatch.setattr(settings_routes, "verify_credentials", fake_verify)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/settings/broker/test")
    body = response.json()
    assert body["ok"] is False
    assert "No API token" in body["detail"]
