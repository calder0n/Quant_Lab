"""Tests for the health endpoint and the app factory."""

import httpx
from fastapi import FastAPI

from quantlab import __version__
from quantlab.config import Settings
from quantlab.container import Container
from quantlab.interfaces.api.app import create_app
from tests.conftest import StubContainer


def build_client(app: FastAPI, container: StubContainer) -> httpx.AsyncClient:
    app.state.container = container
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_health_reports_ok_when_all_components_respond(settings: Settings) -> None:
    app = create_app(settings)
    async with build_client(app, StubContainer(settings)) as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["environment"] == "test"
    assert {name: c["status"] for name, c in body["components"].items()} == {
        "api": "ok",
        "database": "ok",
        "redis": "ok",
    }


async def test_health_degrades_when_database_fails(settings: Settings) -> None:
    app = create_app(settings)
    container = StubContainer(settings, db_error=ConnectionError("db down"))
    async with build_client(app, container) as client:
        response = await client.get("/api/v1/health")
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"]["status"] == "error"
    assert "db down" in body["components"]["database"]["detail"]
    assert body["components"]["redis"]["status"] == "ok"


async def test_health_degrades_when_redis_fails(settings: Settings) -> None:
    app = create_app(settings)
    container = StubContainer(settings, redis_error=TimeoutError("redis timeout"))
    async with build_client(app, container) as client:
        response = await client.get("/api/v1/health")
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["redis"]["status"] == "error"


async def test_lifespan_attaches_and_closes_the_container(settings: Settings) -> None:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.container, Container)
        assert app.state.container.settings is settings


def test_create_app_uses_default_settings_when_none_given() -> None:
    app = create_app()
    assert app.title == "QuantLab"
