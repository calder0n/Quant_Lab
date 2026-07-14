"""FastAPI application factory.

Run with: ``uvicorn quantlab.interfaces.api.app:create_app --factory``.
The factory pattern keeps the app free of import-time side effects and lets
tests build isolated instances with custom settings.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from quantlab import __version__
from quantlab.config import Settings
from quantlab.container import Container
from quantlab.interfaces.api.routes import (
    backtests,
    datasets,
    health,
    optimizations,
    strategies,
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
        try:
            yield
        finally:
            await container.aclose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    app.include_router(health.router, prefix=app_settings.api_v1_prefix)
    app.include_router(datasets.router, prefix=app_settings.api_v1_prefix)
    app.include_router(strategies.router, prefix=app_settings.api_v1_prefix)
    app.include_router(backtests.router, prefix=app_settings.api_v1_prefix)
    app.include_router(settings_routes.router, prefix=app_settings.api_v1_prefix)
    app.include_router(optimizations.router, prefix=app_settings.api_v1_prefix)
    app.include_router(validations.router, prefix=app_settings.api_v1_prefix)
    app.include_router(workers.router, prefix=app_settings.api_v1_prefix)
    return app
