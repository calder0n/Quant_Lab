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
    group: str = "strategy"  # "strategy" | "risk" | "filter" — for UI grouping


@dataclass(frozen=True)
class StrategyMetadata:
    """Static description of a strategy plugin."""

    strategy_id: str
    name: str
    category: str
    description: str
    parameters: tuple[ParameterSpec, ...] = field(default_factory=tuple)


# Risk/filter parameters shared by every strategy. Strategies add their own on top.
# Each entry filter has its own on/off toggle so it can be enabled or disabled
# independently; a filter's numeric parameters only take effect when its toggle is on.
RISK_PARAMS: tuple[ParameterSpec, ...] = (
    ParameterSpec("atr_period", "int", 14, 5, 50, group="risk"),
    ParameterSpec("sl_atr", "float", 2.0, 0.5, 10.0, group="risk"),
    ParameterSpec("tp_atr", "float", 3.0, 0.5, 15.0, group="risk"),
    # Fixed pip distances (0 = off). When set, they override the ATR-based
    # distance for that leg; pip size comes from the instrument being traded.
    ParameterSpec("sl_pips", "float", 0.0, 0.0, 100_000.0, group="risk"),
    ParameterSpec("tp_pips", "float", 0.0, 0.0, 100_000.0, group="risk"),
    ParameterSpec("use_trailing", "bool", False, group="risk"),
    # Cap SL/TP distance to this many *prior-day* daily-ATRs (0 = no cap). Keeps
    # stops/targets within a realistic day's move instead of a far intraday-ATR
    # multiple; uses the previous day's daily ATR so there is no lookahead.
    ParameterSpec("max_atr_days", "float", 0.0, 0.0, 10.0, step=0.5, group="risk"),
    # Session-hour filter: only enter between session_start and session_end (UTC).
    ParameterSpec("use_session_filter", "bool", False, group="filter"),
    ParameterSpec("session_start", "int", 0, 0, 23, group="filter"),
    ParameterSpec("session_end", "int", 23, 0, 23, group="filter"),
    # Abnormal-spread filter: skip entries when the spread spikes above normal.
    ParameterSpec("use_spread_filter", "bool", True, group="filter"),
    ParameterSpec("max_spread_mult", "float", 3.0, 1.0, 10.0, group="filter"),
    # Trend filter (directional): longs only above the trend EMA, shorts only below.
    ParameterSpec("use_trend_filter", "bool", False, group="filter"),
    ParameterSpec("trend_ema", "int", 200, 20, 400, group="filter"),
    # Minimum-volatility filter: skip entries when ATR/price is below the threshold.
    ParameterSpec("use_volatility_filter", "bool", False, group="filter"),
    ParameterSpec("min_atr_pct", "float", 0.0005, 0.0, 0.02, step=0.0001, group="filter"),
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
        """Default execution plan: ATR-multiple stop loss / take profit.

        When ``max_atr_days`` is set, both the SL and TP distances are capped to
        that many daily ATRs so they never reach further than a realistic day's
        move (the far intraday-ATR targets that never fill). ``sl_pips`` /
        ``tp_pips`` (when > 0) replace the ATR-based distance for that leg with a
        fixed pip distance; the instrument's pip size is provided by the caller
        via ``data.attrs["pip_size"]``.
        """
        average_range = ta.atr(data, int(self.params["atr_period"]))
        sl_dist = float(self.params["sl_atr"]) * average_range
        tp_dist = float(self.params["tp_atr"]) * average_range
        max_atr_days = float(self.params["max_atr_days"])
        if max_atr_days > 0:
            # ``clip(upper=cap)`` is elementwise; a NaN cap (early bars with no
            # prior day yet) leaves that bar's distance unclipped.
            cap = max_atr_days * self._daily_atr(data)
            sl_dist = sl_dist.clip(upper=cap)
            tp_dist = tp_dist.clip(upper=cap)
        pip_size = float(data.attrs.get("pip_size", 0.0))
        if pip_size > 0:
            if float(self.params["sl_pips"]) > 0:
                sl_dist = pd.Series(float(self.params["sl_pips"]) * pip_size, index=data.index)
            if float(self.params["tp_pips"]) > 0:
                tp_dist = pd.Series(float(self.params["tp_pips"]) * pip_size, index=data.index)
        sl_pct = (sl_dist / data["close"]).clip(lower=1e-6)
        tp_pct = (tp_dist / data["close"]).clip(lower=1e-6)
        return OrderPlan(sl_pct=sl_pct, tp_pct=tp_pct, trailing=bool(self.params["use_trailing"]))

    def _daily_atr(self, data: pd.DataFrame) -> pd.Series:
        """Previous day's daily ATR, forward-filled onto the intraday index.

        Resamples to daily bars, takes the ATR, then shifts by one day so each
        intraday bar only sees days that have already closed (no lookahead).
        """
        assert isinstance(data.index, pd.DatetimeIndex)
        daily = (
            data.resample("1D")
            .agg({"high": "max", "low": "min", "close": "last"})
            .dropna()
        )
        prior_day_atr = ta.atr(daily, int(self.params["atr_period"])).shift(1)
        return prior_day_atr.reindex(data.index, method="ffill")

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
        """Assemble the signal frame, applying whichever entry filters are enabled."""

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
        long_ok, short_ok = allowed.copy(), allowed.copy()
        if bool(self.params["use_trend_filter"]):
            trend = ta.ema(data["close"], int(self.params["trend_ema"]))
            long_ok &= data["close"] > trend
            short_ok &= data["close"] < trend
        frame["long_entry"] &= long_ok
        frame["short_entry"] &= short_ok
        return frame

    def _entries_allowed(self, data: pd.DataFrame) -> pd.Series:
        """Symmetric entry filters (applied to both long and short) that are enabled."""
        index = data.index
        assert isinstance(index, pd.DatetimeIndex)
        allowed = pd.Series(True, index=index)
        if bool(self.params["use_session_filter"]):
            start = int(self.params["session_start"])
            end = int(self.params["session_end"])
            hours = pd.Series(index.hour, index=index)
            if start <= end:
                allowed &= (hours >= start) & (hours <= end)
            else:  # session wraps around midnight
                allowed &= (hours >= start) | (hours <= end)
        if bool(self.params["use_spread_filter"]) and "spread" in data.columns:
            typical_spread = data["spread"].rolling(500, min_periods=20).median()
            spread_ok = data["spread"] <= float(self.params["max_spread_mult"]) * typical_spread
            allowed &= spread_ok.fillna(True)
        if bool(self.params["use_volatility_filter"]):
            atr_pct = self.atr(data) / data["close"]
            allowed &= (atr_pct >= float(self.params["min_atr_pct"])).fillna(False)
        return allowed

    def chart_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        """Every price-scale line to draw on the chart: strategy logic + active filters."""
        overlays = dict(self.plot_overlays(data))
        if bool(self.params["use_trend_filter"]):
            overlays["Trend EMA"] = ta.ema(data["close"], int(self.params["trend_ema"]))
        return overlays

    def atr(self, data: pd.DataFrame) -> pd.Series:
        return ta.atr(data, int(self.params["atr_period"]))
