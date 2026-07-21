"""Tests for OANDA credential verification (mock transport, no network)."""

import httpx

from quantlab.domain.broker import BrokerCredentials
from quantlab.infrastructure.brokers.oanda.verification import verify_credentials


def http_with(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://x", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def accounts_response(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v3/accounts"
    return httpx.Response(200, json={"accounts": [{"id": "001-1"}, {"id": "001-2"}]})


async def test_valid_token_connects_and_lists_accounts() -> None:
    credentials = BrokerCredentials(api_token="valid-token-123")
    result = await verify_credentials(credentials, http=http_with(accounts_response))
    assert result.ok
    assert result.accounts == ["001-1", "001-2"]
    assert "practice" in result.detail


async def test_matching_account_id_is_accepted() -> None:
    credentials = BrokerCredentials(api_token="valid-token-123", account_id="001-2")
    result = await verify_credentials(credentials, http=http_with(accounts_response))
    assert result.ok


async def test_unknown_account_id_is_rejected() -> None:
    credentials = BrokerCredentials(api_token="valid-token-123", account_id="999-9")
    result = await verify_credentials(credentials, http=http_with(accounts_response))
    assert not result.ok
    assert "999-9" in result.detail
    assert result.accounts == ["001-1", "001-2"]  # shown so the user can pick one


async def test_invalid_token_reports_api_error() -> None:
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    result = await verify_credentials(
        BrokerCredentials(api_token="bad-token-123"), http=http_with(unauthorized)
    )
    assert not result.ok
    assert "401" in result.detail


async def test_network_failure_is_reported() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = await verify_credentials(
        BrokerCredentials(api_token="valid-token-123"), http=http_with(broken)
    )
    assert not result.ok
    assert "Connection failed" in result.detail


async def test_missing_token_short_circuits() -> None:
    result = await verify_credentials(BrokerCredentials())
    assert not result.ok
    assert "No API token" in result.detail
