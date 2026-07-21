"""Tests for quantlab.application.event_bus."""

from dataclasses import dataclass

import pytest

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class DatasetDownloaded(DomainEvent):
    symbol: str


@dataclass(frozen=True, kw_only=True)
class OptimizationFinished(DomainEvent):
    study: str


async def test_publish_dispatches_to_subscribed_handler() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe(DatasetDownloaded, handler)
    event = DatasetDownloaded(symbol="EURUSD")
    await bus.publish(event)
    assert received == [event]


async def test_publish_ignores_unrelated_event_types() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe(DatasetDownloaded, handler)
    await bus.publish(OptimizationFinished(study="s1"))
    assert received == []


async def test_subscribing_to_base_class_receives_all_events() -> None:
    bus = InMemoryEventBus()
    received: list[str] = []

    async def audit(event: DomainEvent) -> None:
        received.append(event.event_name)

    bus.subscribe(DomainEvent, audit)
    await bus.publish(DatasetDownloaded(symbol="EURUSD"))
    await bus.publish(OptimizationFinished(study="s1"))
    assert received == ["DatasetDownloaded", "OptimizationFinished"]


async def test_failing_handler_does_not_block_others(caplog: pytest.LogCaptureFixture) -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []

    async def broken(event: DomainEvent) -> None:
        raise RuntimeError("boom")

    async def healthy(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe(DatasetDownloaded, broken)
    bus.subscribe(DatasetDownloaded, healthy)
    with caplog.at_level("ERROR"):
        await bus.publish(DatasetDownloaded(symbol="EURUSD"))
    assert len(received) == 1
    assert any("failed while handling" in message for message in caplog.messages)


async def test_publish_without_subscribers_is_a_noop() -> None:
    bus = InMemoryEventBus()
    await bus.publish(DatasetDownloaded(symbol="EURUSD"))
