"""Users, roles and API keys."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"  # full control: launch work, change settings, trade
    VIEWER = "viewer"  # read-only dashboards


@dataclass
class User:
    username: str
    role: Role = Role.VIEWER
    password_hash: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None


@dataclass
class ApiKey:
    """A programmatic credential; only its SHA-256 hash is stored."""

    user_id: uuid.UUID
    name: str
    prefix: str  # first characters, for identification in lists
    key_hash: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None


class AuthError(Exception):
    """Raised on failed authentication or authorization."""
