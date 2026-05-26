from abc import ABC, abstractmethod
from typing import Any

from lib.auth.user import AuthUserMixin
from lib.logger import get_logger

logger = get_logger("lib.auth.authorization")


class AbstractAuthorizationBackend(ABC):
    """
    Contract all authorization backends must satisfy.

    Abstract methods every backend must implement:
        authorize(user, action, resource)  → bool
        get_permissions(user)              → set[str]
        registration_defaults()            → dict[str, Any]

    The helper authorize_or_raise() is provided and delegates to authorize().

    registration_defaults() is called during user registration to seed
    initial authorization data (roles, permissions, policies, …) on newly
    created user records.  The returned dict is filtered to keys that actually
    exist on the configured user model before being applied.
    """

    @abstractmethod
    async def authorize(
        self,
        user: AuthUserMixin,
        action: str,
        resource: Any = None,
    ) -> bool:
        """
        Return True if `user` may perform `action` on `resource`.

        action   — dot or colon-separated string, e.g. "posts:edit", "delete"
        resource — the object being acted on; None for global actions
        """
        ...

    @abstractmethod
    async def get_permissions(self, user: AuthUserMixin) -> set[str]:
        """
        Return the full effective permission set for this user.
        Used by require_permission() and the /me endpoint to expose scopes.
        """
        ...

    @abstractmethod
    def registration_defaults(self) -> dict[str, Any]:
        """
        Return default user attributes to stamp onto new user records at registration.

        Called by get_authorization_registration_defaults() which filters the
        result to keys that exist on the configured user model, so returning
        extra keys is safe.

        Expected return shapes per built-in backend:
            RBACBackend   → {"roles": ["viewer"]}
            PBACBackend   → {"roles": ["member"], "permissions": ["posts:read"]}
            PolicyBackend → {} (PolicyBackend doesn't use flat roles/permissions, so no defaults, to set default policies use the `backend.set_default_policy()` method instead)

        Custom backends should document which keys they return and ensure the
        """
        ...

    async def authorize_or_raise(
        self,
        user: AuthUserMixin,
        action: str,
        resource: Any = None,
    ) -> None:
        """
        Authorise or raise PermissionDenied.
        Call from route handlers after Depends(require_auth).
        """
        from lib.auth.exceptions import PermissionDenied

        if not await self.authorize(user, action, resource):
            logger.warning(
                "Authorization denied: user=%s action=%r resource=%r",
                user.get_id(),
                action,
                type(resource).__name__,
            )
            raise PermissionDenied(f"You do not have permission to perform '{action}' on this resource.")
