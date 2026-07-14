"""Tests for the configurable objective function."""

import pytest

from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.objective import (
    DEFAULT_WEIGHTS,
    NORMALIZERS,
    PENALTY_SCORE,
    InvalidObjectiveError,
    ObjectiveConfig,
    compute_score,
)

GOOD = BacktestMetrics(
    total_return=0.8,
    cagr=0.3,
    profit_factor=2.2,
    sharpe=1.8,
    sortino=2.5,
    calmar=2.0,
    max_drawdown=0.12,
    recovery_factor=6.0,
    expectancy=45.0,
    win_rate=0.58,
    avg_trade_return=0.004,
    trades=180,
)
BAD = BacktestMetrics(
    total_return=-0.4,
    cagr=-0.2,
    profit_factor=0.6,
    sharpe=-0.9,
    sortino=-1.2,
    calmar=-0.8,
    max_drawdown=0.55,
    recovery_factor=-1.0,
    expectancy=-20.0,
    win_rate=0.3,
    avg_trade_return=-0.003,
    trades=150,
)


def test_default_objective_ranks_good_above_bad() -> None:
    config = ObjectiveConfig()
    assert compute_score(GOOD, config) > compute_score(BAD, config)
    assert -1.0 <= compute_score(BAD, config) <= 1.0
    assert -1.0 <= compute_score(GOOD, config) <= 1.0


def test_min_trades_constraint_penalizes() -> None:
    config = ObjectiveConfig(min_trades=200)
    assert compute_score(GOOD, config) == PENALTY_SCORE


def test_max_drawdown_constraint_penalizes() -> None:
    config = ObjectiveConfig(max_drawdown_limit=0.10)
    assert compute_score(GOOD, config) == PENALTY_SCORE  # GOOD has 12% DD
    relaxed = ObjectiveConfig(max_drawdown_limit=0.50)
    assert compute_score(GOOD, relaxed) > PENALTY_SCORE


def test_custom_weights_change_the_ranking() -> None:
    high_winrate = BacktestMetrics(win_rate=0.9, sharpe=0.1, trades=100)
    high_sharpe = BacktestMetrics(win_rate=0.35, sharpe=2.5, trades=100)
    winrate_only = ObjectiveConfig(weights={"win_rate": 1.0})
    sharpe_only = ObjectiveConfig(weights={"sharpe": 1.0})
    assert compute_score(high_winrate, winrate_only) > compute_score(high_sharpe, winrate_only)
    assert compute_score(high_sharpe, sharpe_only) > compute_score(high_winrate, sharpe_only)


def test_unknown_metric_is_rejected() -> None:
    with pytest.raises(InvalidObjectiveError, match="Unknown objective metrics"):
        ObjectiveConfig(weights={"nope": 1.0})


def test_empty_or_zero_weights_are_rejected() -> None:
    with pytest.raises(InvalidObjectiveError):
        ObjectiveConfig(weights={})
    with pytest.raises(InvalidObjectiveError):
        ObjectiveConfig(weights={"sharpe": 0.0})


def test_every_default_weight_has_a_normalizer() -> None:
    assert set(DEFAULT_WEIGHTS) <= set(NORMALIZERS)
    for normalizer in NORMALIZERS.values():
        value = normalizer(GOOD)
        assert -1.0 <= value <= 1.0


def test_round_trip_serialization() -> None:
    config = ObjectiveConfig(
        weights={"sharpe": 0.5, "trades": 0.5}, min_trades=10, max_drawdown_limit=0.3
    )
    restored = ObjectiveConfig.from_dict(config.to_dict())
    assert restored == config
    assert ObjectiveConfig.from_dict({}) == ObjectiveConfig()
