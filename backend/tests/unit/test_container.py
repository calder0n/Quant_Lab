"""Tests for the composition root."""

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.config import Settings
from quantlab.container import Container


def test_resources_are_lazy_singletons(settings: Settings) -> None:
    container = Container(settings)
    assert container.engine is container.engine
    assert container.session_factory is container.session_factory
    assert container.redis is container.redis
    assert container.event_bus is container.event_bus
    assert isinstance(container.event_bus, InMemoryEventBus)
    assert container.market_data_provider is container.market_data_provider
    assert container.candle_store is container.candle_store
    assert container.data_ingestion is container.data_ingestion


def test_market_data_provider_is_the_oanda_adapter(settings: Settings) -> None:
    container = Container(settings)
    assert container.market_data_provider.name == "oanda"


def test_settings_are_exposed(settings: Settings) -> None:
    assert Container(settings).settings is settings


async def test_aclose_before_any_access_is_safe(settings: Settings) -> None:
    await Container(settings).aclose()


async def test_aclose_releases_created_resources(settings: Settings) -> None:
    container = Container(settings)
    engine = container.engine
    _ = container.session_factory
    _ = container.redis
    provider = container.market_data_provider
    await container.aclose()
    # After closing, resources are rebuilt on next access.
    assert container.engine is not engine
    assert container.market_data_provider is not provider
