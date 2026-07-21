"""FastAPI dependency helpers bridging requests to the composition root."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.container import Container
from quantlab.domain.auth import AuthError, Role, User


def get_container(request: Request) -> Container:
    """Return the process-wide container attached during application startup."""
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_current_user(request: Request, container: ContainerDep) -> User:
    """Authenticate via Bearer JWT or X-API-Key.

    With ``QL_AUTH_ENABLED=false`` (local development) every request acts as a
    built-in admin.
    """
    if not container.settings.auth_enabled:
        return User(username="local", role=Role.ADMIN)
    authorization = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")
    try:
        if authorization.startswith("Bearer "):
            return await container.auth_service.authenticate_token(
                authorization.removeprefix("Bearer ")
            )
        if api_key:
            return await container.auth_service.authenticate_api_key(api_key)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    """Yield a database session scoped to the current request."""
    async with container.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
