"""Credential verification against the live OANDA API."""

from dataclasses import dataclass, field

import httpx

from quantlab.domain.broker import BrokerCredentials
from quantlab.infrastructure.brokers.oanda.client import OandaApiError, OandaClient


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of a connection test."""

    ok: bool
    detail: str
    accounts: list[str] = field(default_factory=list)


async def verify_credentials(
    credentials: BrokerCredentials, http: httpx.AsyncClient | None = None
) -> VerificationResult:
    """Check the token by listing accounts; validate the account id if set."""
    if not credentials.api_token:
        return VerificationResult(ok=False, detail="No API token configured.")
    client = OandaClient(credentials.api_token, credentials.environment, http=http)
    try:
        accounts = await client.list_accounts()
    except OandaApiError as exc:
        return VerificationResult(ok=False, detail=str(exc))
    except httpx.HTTPError as exc:
        return VerificationResult(ok=False, detail=f"Connection failed: {exc}")
    finally:
        await client.aclose()
    account_ids = [str(account["id"]) for account in accounts]
    if credentials.account_id and credentials.account_id not in account_ids:
        return VerificationResult(
            ok=False,
            detail=f"Token is valid but account {credentials.account_id!r} was not found.",
            accounts=account_ids,
        )
    return VerificationResult(
        ok=True,
        detail=f"Connected to OANDA {credentials.environment}.",
        accounts=account_ids,
    )
