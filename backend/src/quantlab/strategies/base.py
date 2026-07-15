"""Strategy plugin contract.

Every plugin implements: ``load()``, ``generate_signals()``, ``generate_orders()``,
``fitness()`` and ``metadata()``. Parameters are declared as ``ParameterSpec``s in
the metadata, which is what the optimization engine (Phase 4) samples from.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

import pandas as pd

from quantlab.domain.backtest import BacktestMetrics, OrderPlan
from quantlab.strategies import indicators as ta

ParamKind = Literal["int", "float", "bool", "categorical"]
ParamValue = int | float | bool | str

SIGNAL_COLUMNS = ["long_entry", "long_exit", "short_entry", "short_exit"]


@dataclass(frozen=True)
class ParameterSpec:
    """One optimizable parameter: its type, bounds/choices and default."""

    name: str
    kind: ParamKind
    default: ParamValue
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class StrategyMetadata:
    """Static description of a strategy plugin."""

    strategy_id: str
    name: str
    category: str
    description: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)


# Risk/filter parameters shared by every strategy. Strategies add their own on top.
RISK_PARAMS: tuple[ParameterSpec, ...] = (
    ParameterSpec("atr_period", "int", 14, 5, 50),
    ParameterSpec("sl_atr", "float", 2.0, 0.5, 10.0),
    ParameterSpec("tp_atr", "float", 3.0, 0.5, 15.0),
    ParameterSpec("use_trailing", "bool", False),
    ParameterSpec("session_start", "int", 0, 0, 23),
    ParameterSpec("session_end", "int", 23, 0, 23),
    ParameterSpec("max_spread_mult", "float", 3.0, 1.0, 10.0),
)


class InvalidParameterError(ValueError):
    """Raised when a strategy receives unknown or out-of-range parameters."""


def _coerce(spec: ParameterSpec, value: ParamValue) -> ParamValue:
    if spec.kind == "int":
        coerced: ParamValue = int(value)
    elif spec.kind == "float":
        coerced = float(value)
    elif spec.kind == "bool":
        coerced = bool(value)
    else:
        coerced = str(value)
        if spec.choices is not None and coerced not in spec.choices:
            raise InvalidParameterError(f"{spec.name}: {coerced!r} not in {spec.choices}")
    if spec.kind in ("int", "float"):
        numeric = float(coerced)
        if spec.low is not None and numeric < spec.low:
            raise InvalidParameterError(f"{spec.name}={numeric} below minimum {spec.low}")
        if spec.high is not None and numeric > spec.high:
            raise InvalidParameterError(f"{spec.name}={numeric} above maximum {spec.high}")
    return coerced


class Strategy(ABC):
    """Base class for every strategy plugin."""

    strategy_id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[str] = "classic"
    description: ClassVar[str] = ""
    PARAMS: ClassVar[tuple[ParameterSpec, ...]] = ()

    def __init__(self, **params: ParamValue) -> None:
        specs = {spec.name: spec for spec in self.metadata().parameters}
        unknown = set(params) - set(specs)
        if unknown:
            raise InvalidParameterError(f"Unknown parameters: {sorted(unknown)}")
        self.params: dict[str, ParamValue] = {
            name: _coerce(spec, params.get(name, spec.default)) for name, spec in specs.items()
        }

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        """Static metadata including the full optimizable parameter space."""
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            name=cls.name,
            category=cls.category,
            description=cls.description,
            parameters=cls.PARAMS + RISK_PARAMS,
        )

    def load(self) -> None:  # noqa: B027 - optional hook, intentionally non-abstract
        """Hook for expensive initialization (models, caches). Default: no-op."""

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return a boolean frame with columns ``SIGNAL_COLUMNS`` aligned to ``data``."""

    def generate_orders(self, data: pd.DataFrame, signals: pd.DataFrame) -> OrderPlan:
        """Default execution plan: ATR-multiple stop loss / take profit."""
        average_range = ta.atr(data, int(self.params["atr_period"]))
        sl_pct = (float(self.params["sl_atr"]) * average_range / data["close"]).clip(lower=1e-6)
        tp_pct = (float(self.params["tp_atr"]) * average_range / data["close"]).clip(lower=1e-6)
        return OrderPlan(sl_pct=sl_pct, tp_pct=tp_pct, trailing=bool(self.params["use_trailing"]))

    def fitness(self, metrics: BacktestMetrics) -> float:
        """Default composite score, bounded to roughly [-1, 1].

        Blends risk-adjusted returns (Sharpe/Sortino/Calmar) with profit factor
        and discounts strategies with too few trades to be statistically
        meaningful. Phase 4 adds fully configurable objective functions.
        """
        if metrics.trades == 0:
            return -1.0
        significance = min(1.0, metrics.trades / 30.0)
        score = (
            0.35 * math.tanh(metrics.sharpe / 2.0)
            + 0.25 * math.tanh(metrics.sortino / 3.0)
            + 0.20 * (min(metrics.profit_factor, 3.0) / 3.0)
            + 0.20 * math.tanh(metrics.calmar / 3.0)
        )
        return score * significance

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        """Price-scale indicator lines that explain this strategy's entries.

        Returned series share the price axis and are drawn on top of the candles
        in the dashboard. Oscillator-based strategies (RSI, MACD, ...) return an
        empty mapping and rely on the entry/exit markers instead. Default: none.
        """
        return {}

    # -- helpers for subclasses ------------------------------------------------

    def _frame(
        self,
        data: pd.DataFrame,
        long_entry: pd.Series | None = None,
        long_exit: pd.Series | None = None,
        short_entry: pd.Series | None = None,
        short_exit: pd.Series | None = None,
    ) -> pd.DataFrame:
        """Assemble the signal frame, applying the session and spread filters."""

        def clean(series: pd.Series | None) -> pd.Series:
            if series is None:
                return pd.Series(False, index=data.index)
            return series.fillna(False).astype(bool)

        frame = pd.DataFrame(
            {
                "long_entry": clean(long_entry),
                "long_exit": clean(long_exit),
                "short_entry": clean(short_entry),
                "short_exit": clean(short_exit),
            }
        )
        allowed = self._entries_allowed(data)
        frame["long_entry"] &= allowed
        frame["short_entry"] &= allowed
        return frame

    def _entries_allowed(self, data: pd.DataFrame) -> pd.Series:
        """Session-hour filter plus abnormal-spread filter (entries only)."""
        index = data.index
        assert isinstance(index, pd.DatetimeIndex)
        start = int(self.params["session_start"])
        end = int(self.params["session_end"])
        hours = pd.Series(index.hour, index=index)
        if start <= end:
            allowed = (hours >= start) & (hours <= end)
        else:  # session wraps around midnight
            allowed = (hours >= start) | (hours <= end)
        if "spread" in data.columns:
            typical_spread = data["spread"].rolling(500, min_periods=20).median()
            spread_ok = data["spread"] <= float(self.params["max_spread_mult"]) * typical_spread
            allowed &= spread_ok.fillna(True)
        return allowed

    def atr(self, data: pd.DataFrame) -> pd.Series:
        return ta.atr(data, int(self.params["atr_period"]))
