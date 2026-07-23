"""Thin async client for the OANDA v20 REST API.

Only this module talks HTTP to OANDA. It knows nothing about QuantLab domain
types: it takes OANDA instrument/granularity strings and returns raw candle
payloads. The adapter in ``market_data.py`` does the translation.
"""

from datetime import datetime
from typing import Any, Literal

import httpx

OandaEnvironment = Literal["practice", "live"]

_BASE_URLS: dict[OandaEnvironment, str] = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

MAX_CANDLES_PER_REQUEST = 5000


class OandaApiError(Exception):
    """Raised when the OANDA API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"OANDA API error {status_code}: {message}")


def _rfc3339(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


class OandaClient:
    """Async HTTP client for OANDA v20 endpoints used by QuantLab."""

    def __init__(
        self,
        api_token: str,
        environment: OandaEnvironment = "practice",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=_BASE_URLS[environment],
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30.0,
        )

    async def get_candles(
        self,
        instrument: str,
        granularity: str,
        from_time: datetime,
        count: int = MAX_CANDLES_PER_REQUEST,
    ) -> list[dict[str, Any]]:
        """Fetch up to ``count`` candles starting at ``from_time`` (mid/bid/ask)."""
        response = await self._http.get(
            f"/v3/instruments/{instrument}/candles",
            params={
                "granularity": granularity,
                "from": _rfc3339(from_time),
                "count": count,
                "price": "MBA",
            },
        )
        if response.status_code != httpx.codes.OK:
            raise OandaApiError(response.status_code, response.text)
        candles: list[dict[str, Any]] = response.json()["candles"]
        return candles

    async def list_accounts(self) -> list[dict[str, Any]]:
        """List the accounts accessible with this token (used to verify credentials)."""
        response = await self._http.get("/v3/accounts")
        if response.status_code != httpx.codes.OK:
            raise OandaApiError(response.status_code, response.text)
        accounts: list[dict[str, Any]] = response.json()["accounts"]
        return accounts

    async def get_account_summary(self, account_id: str) -> dict[str, Any]:
        response = await self._http.get(f"/v3/accounts/{account_id}/summary")
        if response.status_code != httpx.codes.OK:
            raise OandaApiError(response.status_code, response.text)
        summary: dict[str, Any] = response.json()["account"]
        return summary

    async def get_open_positions(self, account_id: str) -> list[dict[str, Any]]:
        response = await self._http.get(f"/v3/accounts/{account_id}/openPositions")
        if response.status_code != httpx.codes.OK:
            raise OandaApiError(response.status_code, response.text)
        positions: list[dict[str, Any]] = response.json()["positions"]
        return positions

    async def create_market_order(
        self,
        account_id: str,
        instrument: str,
        units: float,
        stop_loss_price: str | None = None,
        take_profit_price: str | None = None,
        trailing_stop_distance: str | None = None,
    ) -> dict[str, Any]:
        """Submit a market order; SL/TP attach to the resulting position on fill.

        ``trailing_stop_distance`` is a price distance; when given it attaches a
        trailing stop (OANDA rejects it alongside a fixed ``stop_loss_price``).
        """
        order: dict[str, Any] = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(int(units)),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
        }
        if stop_loss_price is not None:
            order["stopLossOnFill"] = {"price": stop_loss_price}
        if trailing_stop_distance is not None:
            order["trailingStopLossOnFill"] = {"distance": trailing_stop_distance}
        if take_profit_price is not None:
            order["takeProfitOnFill"] = {"price": take_profit_price}
        response = await self._http.post(f"/v3/accounts/{account_id}/orders", json={"order": order})
        if response.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
            raise OandaApiError(response.status_code, response.text)
        result: dict[str, Any] = response.json()
        return result

    async def get_transactions_since(
        self, account_id: str, since_id: str
    ) -> dict[str, Any]:
        """Every transaction after ``since_id`` (plus the current lastTransactionID)."""
        response = await self._http.get(
            f"/v3/accounts/{account_id}/transactions/sinceid", params={"id": since_id}
        )
        if response.status_code != httpx.codes.OK:
            raise OandaApiError(response.status_code, response.text)
        result: dict[str, Any] = response.json()
        return result

    async def close_position(
        self, account_id: str, instrument: str, long_units: bool, short_units: bool
    ) -> dict[str, Any]:
        payload: dict[str, str] = {}
        if long_units:
            payload["longUnits"] = "ALL"
        if short_units:
            payload["shortUnits"] = "ALL"
        response = await self._http.put(
            f"/v3/accounts/{account_id}/positions/{instrument}/close", json=payload
        )
        if response.status_code != httpx.codes.OK:
            raise OandaApiError(response.status_code, response.text)
        result: dict[str, Any] = response.json()
        return result

    async def aclose(self) -> None:
        await self._http.aclose()
