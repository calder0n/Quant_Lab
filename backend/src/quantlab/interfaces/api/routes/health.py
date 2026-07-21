"""System health endpoint.

Reports the status of the API itself plus each backing service (PostgreSQL,
Redis). Every probe runs under a timeout so a hung dependency degrades the
response instead of hanging it. This endpoint feeds the dashboard's system
status panel.
"""

import asyncio
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from quantlab import __version__
from quantlab.container import Container
from quantlab.interfaces.api.deps import ContainerDep

router = APIRouter(tags=["system"])

ComponentState = Literal["ok", "error"]


class ComponentStatus(BaseModel):
    """Health of a single backing service."""

    status: ComponentState
    detail: str | None = None


class HealthResponse(BaseModel):
    """Aggregated system health."""

    status: Literal["ok", "degraded"]
    version: str
    environment: str
    components: dict[str, ComponentStatus]


async def check_database(container: Container) -> None:
    """Probe PostgreSQL with a trivial round-trip query."""
    async with container.session_factory() as session:
        await session.execute(text("SELECT 1"))


async def check_redis(container: Container) -> None:
    """Probe Redis connectivity."""
    await container.redis.ping()


async def _run_probe(
    probe: asyncio.Future[None] | asyncio.Task[None], timeout: float
) -> ComponentStatus:
    try:
        await asyncio.wait_for(probe, timeout=timeout)
    except Exception as exc:  # any failure, including timeout, means "unhealthy"
        return ComponentStatus(status="error", detail=f"{type(exc).__name__}: {exc}")
    return ComponentStatus(status="ok")


@router.get("/health", response_model=HealthResponse)
async def health(container: ContainerDep) -> HealthResponse:
    """Return the health of the API and its backing services."""
    timeout = container.settings.health_check_timeout_seconds
    database, redis = await asyncio.gather(
        _run_probe(asyncio.ensure_future(check_database(container)), timeout),
        _run_probe(asyncio.ensure_future(check_redis(container)), timeout),
    )
    components = {"api": ComponentStatus(status="ok"), "database": database, "redis": redis}
    degraded = any(component.status != "ok" for component in components.values())
    return HealthResponse(
        status="degraded" if degraded else "ok",
        version=__version__,
        environment=container.settings.environment,
        components=components,
    )
