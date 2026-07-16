"""FastAPI application factory.

Run with: ``uvicorn quantlab.interfaces.api.app:create_app --factory``.
The factory pattern keeps the app free of import-time side effects and lets
tests build isolated instances with custom settings.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from quantlab import __version__
from quantlab.config import Settings
from quantlab.container import Container
from quantlab.infrastructure.logging.redis_handler import (
    setup_dashboard_logging,
    teardown_dashboard_logging,
)
from quantlab.interfaces.api.deps import get_current_user
from quantlab.interfaces.api.routes import (
    auth,
    autotraders,
    backtests,
    datasets,
    health,
    ml,
    optimizations,
    results,
    strategies,
    trading,
    validations,
    workers,
)
from quantlab.interfaces.api.routes import settings as settings_routes


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the QuantLab API application."""
    app_settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container(app_settings)
        app.state.container = container
        log_handler = setup_dashboard_logging(app_settings.redis_url, source="api")
        try:
            yield
        finally:
            teardown_dashboard_logging(log_handler)
            await container.aclose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    # Public: health (docker/uptime checks) and the auth endpoints themselves.
    app.include_router(health.router, prefix=app_settings.api_v1_prefix)
    app.include_router(auth.router, prefix=app_settings.api_v1_prefix)
    # Everything else requires an authenticated user (admin for mutations).
    authenticated = [Depends(get_current_user)]
    for router in (
        datasets.router,
        strategies.router,
        backtests.router,
        settings_routes.router,
        optimizations.router,
        validations.router,
        ml.router,
        results.router,
        workers.router,
        trading.router,
        autotraders.router,
    ):
        app.include_router(router, prefix=app_settings.api_v1_prefix, dependencies=authenticated)
    return app
