"""Base domain event.

Every cross-module notification in QuantLab (dataset downloaded, optimization
finished, order filled, ...) is modelled as an immutable subclass of
``DomainEvent`` and dispatched through the application event bus, keeping
modules decoupled from one another.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Base class for all domain events."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurred_at: datetime = field(default_factory=_utcnow)

    @property
    def event_name(self) -> str:
        """Stable, human-readable identifier of the concrete event type."""
        return type(self).__name__
