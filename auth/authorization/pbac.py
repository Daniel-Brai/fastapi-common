from lib.auth.authorization.base import AbstractAuthorizationBackend
from lib.auth.authorization.rbac import RBACBackend


class PBACBackend(AbstractAuthorizationBackend):
    """
    Permission-Based Access Control.

    Permissions can be granted in two ways:
      1. Directly on the user i.e user.permissions = ["posts:read"]
      2. Via role mapping i.e user.roles = ["editor"] where editor has ["posts:*"]

    Parameters
    ----------
    role_permissions:
        Mapping of role name → list of permission strings.
    default_roles:
        Roles assigned to every new user at registration via
        registration_defaults().  Defaults to an empty list.
    default_permissions:
        Direct permissions assigned to every new user at registration via
        registration_defaults().  Defaults to an empty list.

    Examples:

        PBACBackend(
            role_permissions={
                "admin":  ["*"],
                "editor": ["posts:create", "posts:edit", "posts:read"],
            },
            default_roles=["editor"],
            default_permissions=["comments:read"],
        )

    Wildcard rules are identical to RBACBackend.
    """

    def __init__(
        self,
        role_permissions: dict[str, list[str]] | None = None,
        *,
        default_roles: list[str] | None = None,
        default_permissions: list[str] | None = None,
    ):
        self._role_permissions: dict[str, list[str]] = role_permissions or {}
        self._default_roles: list[str] = list(default_roles or [])
        self._default_permissions: list[str] = list(default_permissions or [])

    async def authorize(self, user, action: str, resource=None) -> bool:
        perms = await self.get_permissions(user)
        return RBACBackend.matches(action, perms)

    async def get_permissions(self, user) -> set[str]:
        perms: set[str] = set(getattr(user, "permissions", None) or [])
        for role in getattr(user, "roles", None) or []:
            perms.update(self._role_permissions.get(role, []))
        return perms

    def registration_defaults(self) -> dict[str, list[str]]:
        return {
            "roles": list(self._default_roles),
            "permissions": list(self._default_permissions),
        }
