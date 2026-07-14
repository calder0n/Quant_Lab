"""Contract tests run against every discovered strategy plugin."""

import pandas as pd
import pytest

from quantlab.strategies.base import SIGNAL_COLUMNS, Strategy
from quantlab.strategies.registry import StrategyRegistry
from tests.factories import make_market_data

REGISTRY = StrategyRegistry().discover()
ALL_IDS = REGISTRY.ids()


@pytest.fixture(scope="module")
def market_data() -> pd.DataFrame:
    return make_market_data(bars=800)


@pytest.mark.parametrize("strategy_id", ALL_IDS)
def test_signals_respect_the_contract(strategy_id: str, market_data: pd.DataFrame) -> None:
    strategy = REGISTRY.create(strategy_id)
    signals = strategy.generate_signals(market_data)
    assert list(signals.columns) == SIGNAL_COLUMNS
    assert signals.index.equals(market_data.index)
    assert signals.dtypes.eq(bool).all()
    assert not signals.isna().any().any()


@pytest.mark.parametrize("strategy_id", ALL_IDS)
def test_signals_are_causal(strategy_id: str, market_data: pd.DataFrame) -> None:
    """Truncating the future must not change past signals (no lookahead)."""
    strategy = REGISTRY.create(strategy_id)
    full = strategy.generate_signals(market_data)
    truncated = strategy.generate_signals(market_data.iloc[:-50])
    overlap = truncated.index
    pd.testing.assert_frame_equal(full.loc[overlap], truncated)


# Permissive parameters for strategies whose default patterns are rare on
# synthetic data; the goal is exercising the signal logic, not tuning.
PERMISSIVE_PARAMS: dict[str, dict[str, float | int | bool | str]] = {
    "ict": {"displacement_atr": 0.5, "killzone_start": 0, "killzone_end": 23},
    "order_blocks": {"displacement_atr": 0.5, "validity_bars": 100},
    "fair_value_gap": {"min_gap_atr": 0.05, "validity_bars": 100},
    "liquidity_sweep": {"min_wick_atr": 0.1, "lookback": 20},
}


@pytest.mark.parametrize("strategy_id", ALL_IDS)
def test_at_least_one_entry_on_rich_data(strategy_id: str, market_data: pd.DataFrame) -> None:
    """Signal logic must produce activity on varied synthetic data."""
    strategy = REGISTRY.create(strategy_id, PERMISSIVE_PARAMS.get(strategy_id))
    signals = strategy.generate_signals(market_data)
    assert (signals["long_entry"] | signals["short_entry"]).any(), (
        f"{strategy_id} produced no entries at all"
    )


@pytest.mark.parametrize("strategy_id", ALL_IDS)
def test_orders_align_with_data(strategy_id: str, market_data: pd.DataFrame) -> None:
    strategy = REGISTRY.create(strategy_id)
    plan = strategy.generate_orders(market_data, strategy.generate_signals(market_data))
    for series in (plan.sl_pct, plan.tp_pct):
        if series is not None:
            assert series.index.equals(market_data.index)
            assert (series.dropna() > 0).all()
    assert 0.0 < plan.size_pct <= 1.0


@pytest.mark.parametrize("strategy_id", ALL_IDS)
def test_strategy_is_deterministic(strategy_id: str, market_data: pd.DataFrame) -> None:
    a = REGISTRY.create(strategy_id).generate_signals(market_data)
    b = REGISTRY.create(strategy_id).generate_signals(market_data)
    pd.testing.assert_frame_equal(a, b)


def test_every_strategy_subclasses_the_contract() -> None:
    for strategy_id in ALL_IDS:
        assert issubclass(REGISTRY.get(strategy_id), Strategy)
