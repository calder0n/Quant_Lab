"""OANDA implementation of the ``ExecutionBroker`` port."""

from quantlab.application.ports import ExecutionBroker
from quantlab.domain.market import Symbol
from quantlab.domain.trading import AccountSummary, BrokerClose, OrderResult, Position
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
        opened = (fill or {}).get("tradeOpened", {})
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
            price=float(fill["price"]) if fill and "price" in fill else None,
            trade_id=str(opened["tradeID"]) if opened.get("tradeID") else None,
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
        closed_trades = fill.get("tradesClosed", [])
        return OrderResult(
            instrument=instrument,
            units=-units,
            filled=bool(fill),
            order_id=str(fill.get("id", "")),
            detail="closed",
            price=float(fill["price"]) if "price" in fill else None,
            realized_pl=float(fill["pl"]) if "pl" in fill else None,
            trade_id=(
                str(closed_trades[0]["tradeID"])
                if closed_trades and closed_trades[0].get("tradeID")
                else None
            ),
        )

    async def settle_closed_trades(self, open_trade_ids: list[str]) -> list[BrokerClose]:
        """Of the given (believed-open) trade ids, those OANDA has since closed.

        Reflects live broker state, so it back-fills SL/TP/trailing exits no
        matter when they happened (robust to worker restarts). The close reason
        is inferred from the P/L sign since a trade record doesn't carry it.
        """
        trades = await self._client.get_trades(self._account_id, open_trade_ids)
        closes: list[BrokerClose] = []
        for trade in trades:
            if trade.get("state") != "CLOSED":
                continue
            realized_pl = float(trade.get("realizedPL", 0.0))
            closing = trade.get("closingTransactionIDs") or [str(trade["id"])]
            closes.append(
                BrokerClose(
                    trade_id=str(trade["id"]),
                    transaction_id=str(closing[-1]),
                    instrument=str(trade.get("instrument", "")),
                    # A close is the opposite side of the opened units.
                    units=-float(trade.get("initialUnits", 0.0)),
                    price=(
                        float(trade["averageClosePrice"])
                        if "averageClosePrice" in trade
                        else None
                    ),
                    realized_pl=realized_pl,
                    reason="take_profit" if realized_pl >= 0 else "stop_loss",
                    time=str(trade.get("closeTime", "")),
                )
            )
        return closes
