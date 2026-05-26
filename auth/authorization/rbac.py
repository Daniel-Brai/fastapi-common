from lib.auth.authorization.base import AbstractAuthorizationBackend


class RBACBackend(AbstractAuthorizationBackend):
    """
    Role-Based Access Control.

    Users have roles (user.roles: list[str]).
    Each role maps to a list of permission strings.
    An action is allowed if any of the user's roles grants it, or grants "*".

    Parameters
    ----------
    role_permissions:
        Mapping of role name and list of permission strings.
    default_roles:
        Roles assigned to every new user at registration via
        registration_defaults().  Defaults to an empty list (no roles).

    Examples:

        RBACBackend(
            {
                "superadmin": ["*"],
                "admin":      ["users:read", "users:write", "posts:*"],
                "editor":     ["posts:create", "posts:edit", "posts:read"],
                "viewer":     ["posts:read"],
            },
            default_roles=["viewer"],
        )

    Wildcard rules:
        `"*"` grants everything and `"posts:*"` grants all actions prefixed with "posts:"
    """

    def __init__(
        self,
        role_permissions: dict[str, list[str]] | None = None,
        *,
        default_roles: list[str] | None = None,
    ):
        self._role_permissions: dict[str, list[str]] = role_permissions or {}
        self._default_roles: list[str] = list(default_roles or [])

    async def authorize(self, user, action: str, resource=None) -> bool:
        perms = await self.get_permissions(user)
        return self.matches(action, perms)

    async def get_permissions(self, user) -> set[str]:
        roles = getattr(user, "roles", None) or []
        perms: set[str] = set()

        for role in roles:
            perms.update(self._role_permissions.get(role, []))

        return perms

    def registration_defaults(self) -> dict[str, list[str]]:
        return {"roles": list(self._default_roles)}

    @staticmethod
    def matches(action: str, perms: set[str]) -> bool:
        if "*" in perms or action in perms:
            return True

        # Prefix wildcard: "posts:*" matches "posts:edit"
        prefix = action.rsplit(":", 1)[0] + ":*" if ":" in action else None
        return bool(prefix and prefix in perms)
