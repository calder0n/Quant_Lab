"""Event bus port and its in-process implementation.

The bus is the only communication channel between decoupled modules. Handlers
subscribe to an event *type*; publishing an event dispatches it to every
handler registered for that type or any of its ancestors, so a handler can
subscribe to ``DomainEvent`` to observe everything (e.g. an audit log).

A failing handler never prevents the remaining handlers from running.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from quantlab.domain.events import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus(ABC):
    """Port for publishing and subscribing to domain events."""

    @abstractmethod
    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Register ``handler`` for events of ``event_type`` (and subclasses)."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Dispatch ``event`` to every matching handler."""


class InMemoryEventBus(EventBus):
    """Simple in-process bus; sufficient until multi-process workers arrive."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = {}

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for event_type, handlers in self._handlers.items():
            if not isinstance(event, event_type):
                continue
            for handler in handlers:
                try:
                    await handler(event)
                except Exception:
                    logger.exception(
                        "Event handler %r failed while handling %s",
                        handler,
                        event.event_name,
                    )
