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

    async def aclose(self) -> None:
        await self._http.aclose()
