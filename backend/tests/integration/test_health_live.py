"""End-to-end health check against live PostgreSQL and Redis.

Runs only inside the docker compose network (``QL_INTEGRATION=1``), where the
``postgres`` and ``redis`` hosts are resolvable.
"""

import os

import httpx
import pytest

from quantlab.config import Settings
from quantlab.interfaces.api.app import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("QL_INTEGRATION") != "1",
        reason="requires live services (set QL_INTEGRATION=1 inside docker compose)",
    ),
]


async def test_health_is_ok_against_live_services() -> None:
    app = create_app(Settings())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert all(component["status"] == "ok" for component in body["components"].values())
