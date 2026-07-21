"""Aggregated research results: global ranking, heatmap and system logs."""

import json
import uuid
from collections.abc import Awaitable
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Query
from pydantic import BaseModel

from quantlab.domain.backtest import BacktestMetrics
from quantlab.infrastructure.logging.redis_handler import LOG_KEY
from quantlab.interfaces.api.deps import ContainerDep
from quantlab.strategies.base import ParamValue

router = APIRouter(tags=["results"])


class RankingEntry(BaseModel):
    study_id: uuid.UUID
    strategy_id: str
    symbol: str
    timeframe: str
    trial_number: int
    score: float
    params: dict[str, ParamValue]
    metrics: BacktestMetrics


class HeatmapCell(BaseModel):
    symbol: str
    timeframe: str
    best_score: float
    studies: int


class LogEntry(BaseModel):
    time: datetime | None = None
    level: str = "INFO"
    source: str = "api"
    logger: str = ""
    message: str = ""


@router.get("/results/ranking", response_model=list[RankingEntry])
async def global_ranking(
    container: ContainerDep, limit: int = Query(20, ge=1, le=100)
) -> list[RankingEntry]:
    """Best trials across every completed study in the lab."""
    async with container.optimization_repository() as repo:
        ranked = await repo.global_ranking(limit=limit)
    return [
        RankingEntry(
            study_id=study.id,
            strategy_id=study.strategy_id,
            symbol=study.symbol.value,
            timeframe=study.timeframe.value,
            trial_number=trial.number,
            score=trial.score,
            params=trial.params,
            metrics=trial.metrics,
        )
        for trial, study in ranked
    ]


@router.get("/results/heatmap", response_model=list[HeatmapCell])
async def results_heatmap(container: ContainerDep) -> list[HeatmapCell]:
    """Best optimization score per market x timeframe."""
    async with container.optimization_repository() as repo:
        cells = await repo.heatmap()
    return [
        HeatmapCell(symbol=symbol, timeframe=timeframe, best_score=best, studies=count)
        for symbol, timeframe, best, count in cells
    ]


@router.get("/logs", response_model=list[LogEntry])
async def recent_logs(
    container: ContainerDep, limit: int = Query(100, ge=1, le=500)
) -> list[LogEntry]:
    """Most recent system log entries (API and workers), newest first."""
    try:
        raw = await cast("Awaitable[list[str]]", container.redis.lrange(LOG_KEY, 0, limit - 1))
    except Exception:
        return []
    entries = []
    for line in raw:
        try:
            entries.append(LogEntry(**json.loads(line)))
        except Exception:
            entries.append(LogEntry(message=str(line)))
    return entries
