"""arq worker definition. Run with: ``arq quantlab.interfaces.worker.settings.WorkerSettings``.

Each worker process owns its own composition root (Container) and executes one
study at a time (``max_jobs=1``: trials are CPU-bound). Scale horizontally with
``docker compose up -d --scale worker=N``.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from arq.connections import RedisSettings

from quantlab.config import Settings
from quantlab.container import Container

OPTIMIZATION_JOB = "run_optimization"
VALIDATION_JOB = "run_validation"
TRAINING_JOB = "train_model"
HEALTH_CHECK_KEY = "arq:quantlab:health-check"
QUEUE_NAME = "arq:quantlab"


def redis_settings(settings: Settings | None = None) -> RedisSettings:
    app_settings = settings if settings is not None else Settings()
    return RedisSettings(
        host=app_settings.redis_host,
        port=app_settings.redis_port,
        database=app_settings.redis_db,
    )


async def startup(ctx: dict[str, Any]) -> None:
    from quantlab.infrastructure.logging.redis_handler import setup_dashboard_logging

    settings = Settings()
    ctx["container"] = Container(settings)
    ctx["log_handler"] = setup_dashboard_logging(settings.redis_url, source="worker")


async def shutdown(ctx: dict[str, Any]) -> None:
    from quantlab.infrastructure.logging.redis_handler import teardown_dashboard_logging

    teardown_dashboard_logging(ctx.get("log_handler"))
    container: Container = ctx["container"]
    await container.aclose()


async def run_optimization(ctx: dict[str, Any], study_id: str) -> str:
    """Execute one optimization study end to end."""
    container: Container = ctx["container"]
    study = await container.optimization_service.run_study(uuid.UUID(study_id))
    return f"{study.strategy_id} {study.symbol} {study.timeframe}: {study.status}"


async def run_validation(ctx: dict[str, Any], run_id: str) -> str:
    """Execute one validation run (walk-forward, Monte Carlo or stress)."""
    container: Container = ctx["container"]
    run = await container.validation_service.run(uuid.UUID(run_id))
    return f"{run.kind} {run.strategy_id} {run.symbol} {run.timeframe}: {run.status}"


async def train_model(ctx: dict[str, Any], model_id: str) -> str:
    """Train one ML model or RL policy."""
    container: Container = ctx["container"]
    model = await container.ml_service.train(uuid.UUID(model_id))
    return f"{model.kind} {model.algorithm} {model.target} {model.symbol}: {model.status}"


class WorkerSettings:
    """arq entrypoint."""

    functions: ClassVar[list[Callable[..., Awaitable[str]]]] = [
        run_optimization,
        run_validation,
        train_model,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    queue_name = QUEUE_NAME
    health_check_key = HEALTH_CHECK_KEY
    health_check_interval = 30
    max_jobs = 1
    job_timeout = 6 * 3600  # generous: large studies over M1 data take hours
