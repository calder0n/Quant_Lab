"""OANDA implementation of the ``ExecutionBroker`` port."""

from quantlab.application.ports import ExecutionBroker
from quantlab.domain.market import Symbol
from quantlab.domain.trading import AccountSummary, OrderResult, Position
from quantlab.infrastructure.brokers.oanda.client import OandaClient
from quantlab.infrastructure.brokers.oanda.market_data import INSTRUMENTS


def _format_price(symbol: Symbol, price: float) -> str:
    decimals = 3 if symbol == Symbol.USDJPY else 5
    if symbol in (Symbol.NAS100, Symbol.SPX500, Symbol.US30, Symbol.XAUUSD):
        decimals = 1
    return f"{price:.{decimals}f}"


class OandaExecutionBroker(ExecutionBroker):
    """Account state and order execution against one OANDA account."""

    def __init__(self, client: OandaClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    async def account_summary(self) -> AccountSummary:
        raw = await self._client.get_account_summary(self._account_id)
        return AccountSummary(
            account_id=str(raw["id"]),
            currency=str(raw["currency"]),
            balance=float(raw["balance"]),
            nav=float(raw["NAV"]),
            margin_used=float(raw["marginUsed"]),
            margin_available=float(raw["marginAvailable"]),
            open_position_count=int(raw["openPositionCount"]),
        )

    async def open_positions(self) -> list[Position]:
        raw = await self._client.get_open_positions(self._account_id)
        positions = []
        for item in raw:
            long_units = float(item["long"]["units"])
            short_units = float(item["short"]["units"])
            units = long_units + short_units  # short units are negative
            side = item["long"] if long_units != 0 else item["short"]
            positions.append(
                Position(
                    symbol=str(item["instrument"]),
                    units=units,
                    average_price=float(side.get("averagePrice", 0.0)),
                    unrealized_pl=float(item.get("unrealizedPL", 0.0)),
                )
            )
        return positions

    async def place_market_order(
        self,
        symbol: Symbol,
        units: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_distance: float | None = None,
    ) -> OrderResult:
        instrument = INSTRUMENTS[symbol]
        raw = await self._client.create_market_order(
            self._account_id,
            instrument,
            units,
            stop_loss_price=_format_price(symbol, stop_loss) if stop_loss else None,
            take_profit_price=_format_price(symbol, take_profit) if take_profit else None,
            trailing_stop_distance=(
                _format_price(symbol, trailing_distance) if trailing_distance else None
            ),
        )
        fill = raw.get("orderFillTransaction")
        create = raw.get("orderCreateTransaction", {})
        return OrderResult(
            instrument=instrument,
            units=units,
            filled=fill is not None,
            order_id=str((fill or create).get("id", "")),
            detail=(
                "filled"
                if fill
                else str(raw.get("orderCancelTransaction", {}).get("reason", "created"))
            ),
        )

    async def close_position(self, symbol: Symbol) -> OrderResult:
        instrument = INSTRUMENTS[symbol]
        positions = await self.open_positions()
        units = next((p.units for p in positions if p.symbol == instrument), 0.0)
        if units == 0:
            return OrderResult(
                instrument=instrument, units=0.0, filled=False, order_id="", detail="no position"
            )
        raw = await self._client.close_position(
            self._account_id, instrument, long_units=units > 0, short_units=units < 0
        )
        fill = raw.get("longOrderFillTransaction") or raw.get("shortOrderFillTransaction") or {}
        return OrderResult(
            instrument=instrument,
            units=-units,
            filled=bool(fill),
            order_id=str(fill.get("id", "")),
            detail="closed",
        )
