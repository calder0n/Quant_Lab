"""Auto-trading worker entrypoint.

Run with: ``python -m quantlab.interfaces.autotrader.runner``. Owns one process
composition root and loops: every ``QL_AUTOTRADER_POLL_SECONDS`` it asks the
auto-trader service to process any enabled assignment whose bar has advanced.
"""

import asyncio
import logging
from datetime import UTC, datetime

from quantlab.config import Settings
from quantlab.container import Container
from quantlab.infrastructure.logging.redis_handler import (
    setup_dashboard_logging,
    teardown_dashboard_logging,
)

logger = logging.getLogger("quantlab.autotrader")


async def run(container: Container, poll_seconds: int, iterations: int | None = None) -> None:
    """Poll loop. ``iterations=None`` runs forever; a finite value aids testing."""
    logger.info("Auto-trader started (poll every %ss)", poll_seconds)
    count = 0
    while iterations is None or count < iterations:
        try:
            await container.auto_trader_service.run_tick(datetime.now(UTC))
        except Exception:
            logger.exception("Auto-trader tick failed")
        count += 1
        if iterations is not None and count >= iterations:
            break
        await asyncio.sleep(poll_seconds)


async def main() -> None:
    settings = Settings()
    container = Container(settings)
    handler = setup_dashboard_logging(settings.redis_url, source="autotrader")
    try:
        await run(container, settings.autotrader_poll_seconds)
    finally:
        teardown_dashboard_logging(handler)
        await container.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
