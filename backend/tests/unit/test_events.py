"""Tests for quantlab.domain.events."""

from dataclasses import dataclass
from datetime import UTC

from quantlab.domain.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class SampleEvent(DomainEvent):
    payload: str


def test_events_get_unique_ids_and_utc_timestamps() -> None:
    first = SampleEvent(payload="a")
    second = SampleEvent(payload="b")
    assert first.event_id != second.event_id
    assert first.occurred_at.tzinfo == UTC


def test_event_name_matches_class_name() -> None:
    assert SampleEvent(payload="x").event_name == "SampleEvent"
