"""Worker fleet status, read from the arq health-check heartbeat in Redis."""

import re

from fastapi import APIRouter
from pydantic import BaseModel

from quantlab.interfaces.api.deps import ContainerDep
from quantlab.interfaces.worker.settings import HEALTH_CHECK_KEY

router = APIRouter(prefix="/workers", tags=["system"])

_COUNTER = re.compile(r"(j_complete|j_failed|j_retried|j_ongoing|queued)=(\d+)")


class WorkersStatus(BaseModel):
    online: bool
    jobs_complete: int = 0
    jobs_failed: int = 0
    jobs_ongoing: int = 0
    queued: int = 0
    heartbeat: str | None = None


@router.get("", response_model=WorkersStatus)
async def workers_status(container: ContainerDep) -> WorkersStatus:
    """Report whether a worker is alive and its job counters.

    arq refreshes a TTL'd health-check key; if it is absent, no worker is running.
    """
    try:
        heartbeat: str | None = await container.redis.get(HEALTH_CHECK_KEY)
    except Exception:
        heartbeat = None
    if not heartbeat:
        return WorkersStatus(online=False)
    counters = {name: int(value) for name, value in _COUNTER.findall(heartbeat)}
    return WorkersStatus(
        online=True,
        jobs_complete=counters.get("j_complete", 0),
        jobs_failed=counters.get("j_failed", 0),
        jobs_ongoing=counters.get("j_ongoing", 0),
        queued=counters.get("queued", 0),
        heartbeat=heartbeat,
    )
