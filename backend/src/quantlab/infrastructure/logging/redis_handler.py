"""Redis-backed ring buffer for dashboard logs.

Every QuantLab process (API, workers) attaches this handler to the
``quantlab`` logger; the dashboard reads the shared capped list. Logging must
never break the application, so every failure here is swallowed.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

LOG_KEY = "quantlab:logs"
MAX_ENTRIES = 500


class SyncRedisLike(Protocol):
    """The minimal sync-redis surface the handler needs (injectable in tests)."""

    def pipeline(self) -> Any: ...


class RedisLogHandler(logging.Handler):
    """Pushes formatted records to a capped Redis list (newest first)."""

    def __init__(self, client: SyncRedisLike, source: str) -> None:
        super().__init__(level=logging.INFO)
        self._client = client
        self._source = source

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = json.dumps(
                {
                    "time": datetime.now(UTC).isoformat(timespec="seconds"),
                    "level": record.levelname,
                    "source": self._source,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
            )
            pipe = self._client.pipeline()
            pipe.lpush(LOG_KEY, entry)
            pipe.ltrim(LOG_KEY, 0, MAX_ENTRIES - 1)
            pipe.execute()
        except Exception:
            pass


def setup_dashboard_logging(redis_url: str, source: str) -> RedisLogHandler | None:
    """Attach the handler to the ``quantlab`` logger. Returns it for teardown."""
    try:
        import redis as redis_sync

        client = redis_sync.Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
        )
    except Exception:
        return None
    handler = RedisLogHandler(client, source)
    logger = logging.getLogger("quantlab")
    logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)
    return handler


def teardown_dashboard_logging(handler: RedisLogHandler | None) -> None:
    if handler is not None:
        logging.getLogger("quantlab").removeHandler(handler)
