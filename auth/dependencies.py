from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from lib.auth.backends.base import AbstractBackend
from lib.auth.config import get_authorization
from lib.auth.exceptions import AuthError, PermissionDenied
from lib.auth.helpers import auth_error_to_http
from lib.auth.openapi import make_openapi_scheme
from lib.auth.user import AuthUserMixin
from lib.logger import get_logger

logger = get_logger("lib.auth.dependencies")


def _prefix_wildcard(action: str, perms: set[str]) -> bool:
    if ":" in action:
        return action.rsplit(":", 1)[0] + ":*" in perms
    return False


def make_auth_dependency(backend: AbstractBackend, raise_exception: bool = True) -> Callable[..., Any]:
    """
    Create a FastAPI dependency that authenticates using the given backend.

    If `raise_exception` is True, it will raise HTTP 401 on authentication failure.

    If `raise_exception` is False, it will return None on authentication failure, allowing the route to handle it (e.g. for optional authentication).

    Examples:

        from lib.auth import make_auth_dependecy, get_backend

        auth_dep = make_auth_dependency(get_backend())

        @app.get("/protected")
        async def protected_route(user = Depends(auth_dep)):
            ...
    """

    openapi_scheme = make_openapi_scheme(backend)

    async def dependency(
        credential: Any | None = Depends(openapi_scheme),
    ) -> AuthUserMixin | None:
        try:
            return await backend.authenticate(credential)
        except AuthError as exc:
            if raise_exception:
                raise auth_error_to_http(exc) from exc

            return None

    return dependency


def require_roles(auth_dep: Callable, *roles: str):
    """
    Dependency factory: user must have AT LEAST ONE of the given roles.

    Examples:

        @app.get("/admin")
        async def panel(user = Depends(require_roles(make_auth_dependency(get_backend()), "admin", "superadmin"))):
            ...
    """

    async def _check(user=Depends(auth_dep)):
        if not any(user.has_role(r) for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these roles is required: {', '.join(roles)}",
            )
        return user

    return _check


def require_permission(auth_dep: Callable, *actions: str) -> Callable:
    """
    Dependency factory: user must have ALL of the given permissions.

    Examples:

        @app.post("/posts")
        async def create(user = Depends(require_permission(make_auth_dependency(get_backend()), "posts:create"))):
            ...
    """

    async def _check(user=Depends(auth_dep)):
        authz = get_authorization()
        if authz is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No authorization backend configured.",
            )

        perms = await authz.get_permissions(user)
        for action in actions:
            if not ("*" in perms or action in perms or _prefix_wildcard(action, perms)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission required: {action}",
                )

        return user

    return _check


def require_any_permission(auth_dep: Callable, *actions: str) -> Callable:
    """
    Dependency factory: user must have AT LEAST ONE of the given permissions.

    Examples:
        @app.get("/dashboard")
        async def dash(user = Depends(require_any_permission(make_auth_dependency(get_backend()), "reports:read", "analytics:read"))):
            ...
    """

    async def _check(user=Depends(auth_dep)):
        authz = get_authorization()
        if authz is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No authorization backend configured.",
            )

        perms = await authz.get_permissions(user)
        if "*" in perms:
            return user

        for action in actions:
            if action in perms or _prefix_wildcard(action, perms):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these permissions is required: {', '.join(actions)}",
        )

    return _check


async def authorize(user: Any, action: str, resource: Any = None) -> None:
    """
    Raise HTTP 403 if the user is not authorised to perform action on resource.

    Works with any authorization backend (RBAC, PBAC, PolicyBackend).

    Examples:

        @router.put("/posts/{post_id}")
        async def update_post(post=..., user=Depends(make_auth_dependency(get_backend()))):
            await authorize(user, "edit", post)
            ...
    """
    authz = get_authorization()
    if authz is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No authorization backend configured.",
        )

    try:
        await authz.authorize_or_raise(user, action, resource)
    except PermissionDenied as exc:
        raise auth_error_to_http(exc) from exc
