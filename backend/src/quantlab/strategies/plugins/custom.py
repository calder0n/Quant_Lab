"""User-composed strategy: combine any of the built-in strategies' signals.

Each component strategy has an on/off toggle; the enabled ones vote on entries
according to ``combine`` (any / majority / all). Exits fire when any enabled
component exits. Risk (SL/TP/trailing) and the shared entry filters come from
the same common parameters every strategy has, so the user assembles a strategy
from existing building blocks without writing code.
"""

import pandas as pd

from quantlab.strategies.base import ParameterSpec, Strategy
from quantlab.strategies.plugins.atr_breakout import AtrBreakout
from quantlab.strategies.plugins.bollinger import BollingerReversion
from quantlab.strategies.plugins.breakout import BufferedBreakout
from quantlab.strategies.plugins.donchian import DonchianBreakout
from quantlab.strategies.plugins.ema_cross import EmaCross
from quantlab.strategies.plugins.fair_value_gap import FairValueGap
from quantlab.strategies.plugins.ict import IctKillzone
from quantlab.strategies.plugins.liquidity_sweep import LiquiditySweep
from quantlab.strategies.plugins.macd import MacdCross
from quantlab.strategies.plugins.mean_reversion import ZScoreReversion
from quantlab.strategies.plugins.opening_range import OpeningRange
from quantlab.strategies.plugins.order_blocks import OrderBlocks
from quantlab.strategies.plugins.rsi import RsiReversion
from quantlab.strategies.plugins.smc import SmartMoneyConcepts
from quantlab.strategies.plugins.vwap import VwapReversion

COMPONENTS: tuple[type[Strategy], ...] = (
    EmaCross,
    MacdCross,
    RsiReversion,
    BollingerReversion,
    ZScoreReversion,
    VwapReversion,
    DonchianBreakout,
    BufferedBreakout,
    AtrBreakout,
    OpeningRange,
    SmartMoneyConcepts,
    FairValueGap,
    OrderBlocks,
    LiquiditySweep,
    IctKillzone,
)


class CustomComposite(Strategy):
    """Combine the signals of the enabled component strategies by vote."""

    strategy_id = "custom"
    name = "Custom (combine strategies)"
    category = "composite"
    description = (
        "Build your own strategy: tick the components whose signals to include and how "
        "to combine their entries (any / majority / all), with the shared risk and "
        "filter parameters applied on top. Components run with their default settings."
    )
    PARAMS = (
        *(
            ParameterSpec(f"use_{component.strategy_id}", "bool", component is EmaCross)
            for component in COMPONENTS
        ),
        ParameterSpec("combine", "categorical", "any", choices=("any", "majority", "all")),
        # RSI component tunables, forwarded when use_rsi is on (same bounds as
        # the standalone RSI strategy).
        ParameterSpec("rsi_period", "int", 14, 2, 50),
        ParameterSpec("rsi_oversold", "float", 30.0, 5.0, 45.0),
        ParameterSpec("rsi_overbought", "float", 70.0, 55.0, 95.0),
    )

    def _component_params(self, component: type[Strategy]) -> dict:
        # Components run with their own entry filters neutralized: the composite
        # applies its single set of shared filters on the combined signal instead.
        params: dict = {"use_spread_filter": False}
        if component is RsiReversion:
            params.update(
                rsi_period=self.params["rsi_period"],
                oversold=self.params["rsi_oversold"],
                overbought=self.params["rsi_overbought"],
            )
        return params

    def _enabled(self) -> list[Strategy]:
        return [
            component(**self._component_params(component))
            for component in COMPONENTS
            if bool(self.params[f"use_{component.strategy_id}"])
        ]

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        components = self._enabled()
        if not components:
            return self._frame(data)

        frames = [component.generate_signals(data) for component in components]
        votes_needed = {
            "any": 1,
            "majority": len(frames) // 2 + 1,
            "all": len(frames),
        }[str(self.params["combine"])]

        def combined(column: str, needed: int) -> pd.Series:
            stacked = sum(frame[column].astype(int) for frame in frames)
            return stacked >= needed

        return self._frame(
            data,
            long_entry=combined("long_entry", votes_needed),
            short_entry=combined("short_entry", votes_needed),
            # Any component's exit closes the position: the first building block
            # that says "get out" wins, keeping exits conservative.
            long_exit=combined("long_exit", 1),
            short_exit=combined("short_exit", 1),
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        overlays: dict[str, pd.Series] = {}
        for component in self._enabled():
            for name, series in component.plot_overlays(data).items():
                overlays[f"{component.strategy_id}: {name}"] = series
        return overlays
