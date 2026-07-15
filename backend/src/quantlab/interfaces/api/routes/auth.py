"""Authentication and user administration endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from quantlab.domain.auth import ApiKey, AuthError, Role, User
from quantlab.interfaces.api.deps import AdminUser, ContainerDep, CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthStatusOut(BaseModel):
    auth_enabled: bool
    initialized: bool


class CredentialsIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class UserCreate(CredentialsIn):
    role: Role = Role.VIEWER


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: Role


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: Role
    created_at: datetime | None

    @classmethod
    def from_entity(cls, user: User) -> "UserOut":
        return cls(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime | None

    @classmethod
    def from_entity(cls, key: ApiKey) -> "ApiKeyOut":
        return cls(id=key.id, name=key.name, prefix=key.prefix, created_at=key.created_at)


class ApiKeyCreated(ApiKeyOut):
    api_key: str  # plaintext, shown exactly once


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.get("/status", response_model=AuthStatusOut)
async def auth_status(container: ContainerDep) -> AuthStatusOut:
    """Public: whether auth is enabled and the first admin exists."""
    initialized = True
    if container.settings.auth_enabled:
        initialized = await container.auth_service.is_initialized()
    return AuthStatusOut(auth_enabled=container.settings.auth_enabled, initialized=initialized)


@router.post("/setup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def setup(body: CredentialsIn, container: ContainerDep) -> TokenOut:
    """Create the first admin user (only while no users exist) and log in."""
    try:
        await container.auth_service.setup_first_admin(body.username, body.password)
        token, user = await container.auth_service.login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TokenOut(access_token=token, username=user.username, role=user.role)


@router.post("/login", response_model=TokenOut)
async def login(body: CredentialsIn, container: ContainerDep) -> TokenOut:
    try:
        token, user = await container.auth_service.login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenOut(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.from_entity(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(_: AdminUser, container: ContainerDep) -> list[UserOut]:
    return [UserOut.from_entity(user) for user in await container.auth_service.list_users()]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, _: AdminUser, container: ContainerDep) -> UserOut:
    try:
        user = await container.auth_service.create_user(body.username, body.password, body.role)
    except AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserOut.from_entity(user)


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(user: CurrentUser, container: ContainerDep) -> list[ApiKeyOut]:
    return [ApiKeyOut.from_entity(key) for key in await container.auth_service.list_api_keys(user)]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate, user: CurrentUser, container: ContainerDep
) -> ApiKeyCreated:
    """Generate an API key; store the value now — it is never shown again."""
    plaintext, key = await container.auth_service.create_api_key(user, body.name)
    return ApiKeyCreated(
        id=key.id, name=key.name, prefix=key.prefix, created_at=key.created_at, api_key=plaintext
    )
