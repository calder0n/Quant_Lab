"""Tests for the composition root."""

import pytest

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.config import Settings
from quantlab.container import Container
from quantlab.domain.broker import BrokerCredentials


@pytest.fixture
def offline_settings() -> Settings:
    """Settings whose database is unreachable, so credential reads fall back to env."""
    return Settings(
        _env_file=None,
        environment="test",
        postgres_host="db-host-that-does-not-exist",
        oanda_api_token="env-token-12345",
        oanda_account_id="001-7",
        oanda_environment="live",
    )


def test_resources_are_lazy_singletons(settings: Settings) -> None:
    container = Container(settings)
    assert container.engine is container.engine
    assert container.session_factory is container.session_factory
    assert container.redis is container.redis
    assert container.event_bus is container.event_bus
    assert isinstance(container.event_bus, InMemoryEventBus)
    assert container.candle_store is container.candle_store
    assert container.strategy_registry is container.strategy_registry
    assert container.backtest_service is container.backtest_service


def test_settings_are_exposed(settings: Settings) -> None:
    assert Container(settings).settings is settings


async def test_credentials_fall_back_to_environment(offline_settings: Settings) -> None:
    container = Container(offline_settings)
    credentials = await container.oanda_credentials()
    assert credentials.api_token == "env-token-12345"
    assert credentials.account_id == "001-7"
    assert credentials.environment == "live"
    await container.aclose()


async def test_provider_is_cached_while_credentials_are_stable(
    offline_settings: Settings,
) -> None:
    container = Container(offline_settings)
    provider = await container.market_data_provider()
    assert provider.name == "oanda"
    assert await container.market_data_provider() is provider
    ingestion = await container.data_ingestion()
    assert await container.data_ingestion() is ingestion
    await container.aclose()


async def test_provider_is_rebuilt_when_credentials_change(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = Container(offline_settings)
    first = await container.market_data_provider()

    async def new_credentials() -> BrokerCredentials:
        return BrokerCredentials(api_token="portal-token-9876", environment="practice")

    monkeypatch.setattr(container, "oanda_credentials", new_credentials)
    second = await container.market_data_provider()
    assert second is not first  # old client closed, new one built for the new token
    assert await container.market_data_provider() is second
    await container.aclose()


async def test_aclose_before_any_access_is_safe(settings: Settings) -> None:
    await Container(settings).aclose()


async def test_aclose_releases_created_resources(offline_settings: Settings) -> None:
    container = Container(offline_settings)
    engine = container.engine
    _ = container.session_factory
    _ = container.redis
    provider = await container.market_data_provider()
    await container.aclose()
    # After closing, resources are rebuilt on next access.
    assert container.engine is not engine
    assert await container.market_data_provider() is not provider
    await container.aclose()
