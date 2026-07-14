"""Tests for the arq worker wiring."""

import uuid

from quantlab.config import Settings
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig
from quantlab.domain.optimization import OptimizationStudy, StudyStatus
from quantlab.interfaces.worker import settings as worker_settings


class FakeService:
    def __init__(self) -> None:
        self.calls: list[uuid.UUID] = []

    async def run_study(self, study_id: uuid.UUID) -> OptimizationStudy:
        self.calls.append(study_id)
        return OptimizationStudy(
            strategy_id="ema_cross",
            symbol=Symbol.EURUSD,
            timeframe=Timeframe.H1,
            optimizer="optuna",
            n_trials=10,
            objective=ObjectiveConfig(),
            status=StudyStatus.COMPLETED,
            id=study_id,
        )


class FakeContainer:
    def __init__(self) -> None:
        self.optimization_service = FakeService()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


async def test_run_optimization_job_delegates_to_the_service() -> None:
    container = FakeContainer()
    ctx: dict[str, object] = {"container": container}
    study_id = uuid.uuid4()
    summary = await worker_settings.run_optimization(ctx, str(study_id))
    assert container.optimization_service.calls == [study_id]
    assert "completed" in summary


async def test_shutdown_closes_the_container() -> None:
    container = FakeContainer()
    ctx: dict[str, object] = {"container": container}
    await worker_settings.shutdown(ctx)
    assert container.closed


def test_redis_settings_come_from_app_settings() -> None:
    settings = Settings(_env_file=None, redis_host="cache.local", redis_port=7000, redis_db=2)
    redis = worker_settings.redis_settings(settings)
    assert redis.host == "cache.local"
    assert redis.port == 7000
    assert redis.database == 2


def test_worker_settings_run_one_job_at_a_time() -> None:
    assert worker_settings.WorkerSettings.max_jobs == 1
    assert worker_settings.WorkerSettings.functions == [worker_settings.run_optimization]
