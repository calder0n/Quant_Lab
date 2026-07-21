"""Broker account settings endpoints.

Lets the portal store OANDA credentials in the database (they take precedence
over environment variables) and test them against the live API. The token is
write-only: responses only ever contain a masked preview.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from quantlab.domain.broker import OANDA, BrokerCredentials, BrokerEnvironment
from quantlab.infrastructure.brokers.oanda.verification import verify_credentials
from quantlab.interfaces.api.deps import AdminUser, ContainerDep

router = APIRouter(prefix="/settings", tags=["settings"])

CredentialSource = Literal["database", "environment", "none"]


class BrokerSettingsOut(BaseModel):
    broker: str
    configured: bool
    source: CredentialSource
    token_preview: str | None
    account_id: str
    environment: BrokerEnvironment
    updated_at: datetime | None


class BrokerSettingsIn(BaseModel):
    """Partial update: omitted fields keep their stored value."""

    api_token: str | None = Field(None, min_length=8)
    account_id: str | None = None
    environment: BrokerEnvironment | None = None


class ConnectionTestOut(BaseModel):
    ok: bool
    detail: str
    accounts: list[str]


async def _resolve(container: ContainerDep) -> tuple[BrokerCredentials, CredentialSource]:
    async with container.broker_settings_repository() as repo:
        stored = await repo.get(OANDA)
    if stored is not None and stored.configured:
        return stored, "database"
    settings = container.settings
    env_credentials = BrokerCredentials(
        api_token=settings.oanda_api_token,
        account_id=settings.oanda_account_id,
        environment=settings.oanda_environment,
    )
    return env_credentials, "environment" if env_credentials.configured else "none"


def _to_out(credentials: BrokerCredentials, source: CredentialSource) -> BrokerSettingsOut:
    return BrokerSettingsOut(
        broker=OANDA,
        configured=credentials.configured,
        source=source,
        token_preview=credentials.token_preview,
        account_id=credentials.account_id,
        environment=credentials.environment,
        updated_at=credentials.updated_at,
    )


@router.get("/broker", response_model=BrokerSettingsOut)
async def get_broker_settings(container: ContainerDep) -> BrokerSettingsOut:
    """Current OANDA configuration (token masked)."""
    credentials, source = await _resolve(container)
    return _to_out(credentials, source)


@router.put("/broker", response_model=BrokerSettingsOut)
async def update_broker_settings(
    body: BrokerSettingsIn, container: ContainerDep, _: AdminUser
) -> BrokerSettingsOut:
    """Store credentials in the database; they override environment variables."""
    async with container.broker_settings_repository() as repo:
        current = await repo.get(OANDA) or BrokerCredentials()
        current.api_token = body.api_token if body.api_token is not None else current.api_token
        current.account_id = body.account_id if body.account_id is not None else current.account_id
        current.environment = (
            body.environment if body.environment is not None else current.environment
        )
        saved = await repo.upsert(current)
    return _to_out(saved, "database" if saved.configured else "none")


@router.delete("/broker", response_model=BrokerSettingsOut)
async def delete_broker_settings(container: ContainerDep, _: AdminUser) -> BrokerSettingsOut:
    """Remove portal-stored credentials (environment variables apply again)."""
    async with container.broker_settings_repository() as repo:
        await repo.delete(OANDA)
    credentials, source = await _resolve(container)
    return _to_out(credentials, source)


@router.post("/broker/test", response_model=ConnectionTestOut)
async def test_broker_connection(container: ContainerDep) -> ConnectionTestOut:
    """Verify the configured credentials against the live OANDA API."""
    credentials, _ = await _resolve(container)
    result = await verify_credentials(credentials)
    return ConnectionTestOut(ok=result.ok, detail=result.detail, accounts=result.accounts)
