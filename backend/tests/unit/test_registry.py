"""Tests for automatic plugin discovery."""

import pytest

from quantlab.strategies.base import Strategy
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError

EXPECTED_STRATEGIES = {
    "ema_cross",
    "rsi",
    "macd",
    "vwap",
    "bollinger",
    "atr_breakout",
    "opening_range",
    "donchian",
    "mean_reversion",
    "breakout",
    "smc",
    "ict",
    "order_blocks",
    "fair_value_gap",
    "liquidity_sweep",
}


@pytest.fixture(scope="module")
def registry() -> StrategyRegistry:
    return StrategyRegistry().discover()


def test_all_fifteen_strategies_are_discovered(registry: StrategyRegistry) -> None:
    assert set(registry.ids()) == EXPECTED_STRATEGIES


def test_metadata_is_complete(registry: StrategyRegistry) -> None:
    for metadata in registry.list_metadata():
        assert metadata.strategy_id
        assert metadata.name
        assert metadata.description
        assert len(metadata.parameters) >= 7  # at least the shared risk params


def test_create_instantiates_and_loads(registry: StrategyRegistry) -> None:
    strategy = registry.create("ema_cross", {"fast_period": 5})
    assert isinstance(strategy, Strategy)
    assert strategy.params["fast_period"] == 5


def test_unknown_strategy_raises(registry: StrategyRegistry) -> None:
    with pytest.raises(UnknownStrategyError):
        registry.get("does_not_exist")
