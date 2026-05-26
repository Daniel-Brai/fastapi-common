from typing import Any

from lib.auth.authorization.base import AbstractAuthorizationBackend
from lib.auth.user import AuthUserMixin
from lib.logger import get_logger

logger = get_logger("lib.auth.authorization.policy")


class BasePolicy:
    """
    Base class for Policy-style resource policies.

    You define one policy per resource type.

    Each policy is a class with can_{action}() methods that return True/False.

    Examples:

        @policy_backend.policy(Post)
        class PostPolicy(BasePolicy):
            def can_view(self)   -> bool: return True
            def can_create(self) -> bool: return self.user.is_active
            def can_edit(self)   -> bool:
                return self.user.is_admin() or self.resource.author_id == self.user.id
            def can_delete(self) -> bool:
                return self.user.is_admin()

    Default implementations (override freely):
        can_view   i.e True for any active user
        can_create i.e True for any active user
        can_edit   i.e True only for admins
        can_delete i.e True only for admins
    """

    #: Set this on the subclass so PolicyBackend.register() knows the type.
    #: The @policy decorator sets it automatically.
    resource_class: type = object

    def __init__(self, user: "AuthUserMixin", resource: Any = None):
        self.user = user
        self.resource = resource

    def can(self, action: str) -> bool:
        """
        Dispatch to can_{action}()

        Returns False for unknown actions (fail-secure).
        """
        method = getattr(self, f"can_{action}", None)
        if method is None:
            logger.debug("No can_%s() on %s — denying", action, type(self).__name__)
            return False

        result = method()
        return bool(result)

    def can_view(self) -> bool:
        return self.user is not None and self.user.is_active

    def can_create(self) -> bool:
        return self.user is not None and self.user.is_active

    def can_edit(self) -> bool:
        return self.user is not None and self.user.is_admin()

    def can_delete(self) -> bool:
        return self.user is not None and self.user.is_admin()


class BaseScope:
    """
    Scope class for filtering querysets based on user permissions.

    Given a user and a base query, return the rows the user is allowed to see.

    Examples:

        @backend.scope(Post)
        class PostScope(BaseScope):
            def resolve(self):
                if self.user.is_admin():
                    return self.query        # see all
                return self.query.where(Post.author_id == self.user.id)

        ##### In a service:
        scope = await get_authorization().scope_for(user, Post, select(Post))
        posts = session.exec(scope.resolve()).all()
    """

    def __init__(self, user: AuthUserMixin, query: Any):
        self.user = user
        self.query = query

    def resolve(self) -> Any:
        """
        Apply user-specific filters to self.query and return it.

        Override in subclasses.
        """

        raise NotImplementedError(f"{type(self).__name__} must implement resolve()")


class PolicyBackend(AbstractAuthorizationBackend):
    """
    Policy-style resource-level authorization.

    Register a BasePolicy subclass for each resource type, then call
    authorize(user, action, resource) from your route handlers.

    Registration — three equivalent styles:

        # 1. Explicit register()
        backend.register(Post, PostPolicy)

        # 2. @policy decorator
        # where @backend = PolicyBackend(...)
        @backend.policy(Post)
        class PostPolicy(BasePolicy): ...

        # 3. resource_class attribute (auto-detected on register)
        class PostPolicy(BasePolicy):
            resource_class = Post

        backend.register_policy(PostPolicy)

    Fallback policy:
    ```python
    backend.set_default_policy(DefaultPolicy)
    ```

    It is used for resource types without a registered policy.

    If unset, access is DENIED for unknown types (fail-secure).

    Scope queries are supported via BaseScope subclasses registered similarly to policies.

    Examples:

    ```python
        @backend.scope(Post)
        class PostScope(BaseScope):
            def resolve(self):
                if self.user.is_admin(): return self.query
                return self.query.where(Post.author_id == self.user.id)

        scope_class = backend.get_scope(Post)
        queryset    = scope_class(user, Post).resolve()
    ```
    """

    def __init__(self):
        self._registry: dict[type, type[BasePolicy]] = {}
        self._scopes: dict[type, type["BaseScope"]] = {}
        self._default_policy: type[BasePolicy] | None = None
        self._default_scope: type["BaseScope"] | None = None

    def register(
        self,
        resource_class: type,
        policy_class: type[BasePolicy],
    ) -> None:
        """
        Register a policy for a resource type.
        """

        self._registry[resource_class] = policy_class

    def register_policy(self, policy_class: type[BasePolicy]) -> None:
        """
        Register a policy class that declares its own resource_class attribute.

        Examples:

            class PostPolicy(BasePolicy):
                resource_class = Post
                def can_edit(self): ...

            backend.register_policy(PostPolicy)
        """

        if policy_class.resource_class is object:
            raise ValueError(f"{policy_class.__name__} must set resource_class = YourModel")

        self.register(policy_class.resource_class, policy_class)

    def register_scope(
        self,
        resource_class: type,
        scope_class: type["BaseScope"],
    ) -> None:
        self._scopes[resource_class] = scope_class

    def set_default_policy(self, policy_class: type[BasePolicy]) -> None:
        """
        Fallback for resource types without an explicit registration.

        Examples:

            class DefaultPolicy(BasePolicy):
                def can_view(self): return True
                def can_create(self): return False
                def can_edit(self): return False
                def can_delete(self): return False

            backend.set_default_policy(DefaultPolicy)
        """

        self._default_policy = policy_class

    def set_default_scope(self, scope_class: type["BaseScope"]) -> None:
        self._default_scope = scope_class

    def policy(self, resource_class: type):
        """
        Decorator to register a policy class.

        Examples:

            @backend.policy(Post)
            class PostPolicy(BasePolicy):
                def can_edit(self): ...
        """

        def decorator(policy_class: type[BasePolicy]) -> type[BasePolicy]:
            self.register(resource_class, policy_class)
            return policy_class

        return decorator

    def scope(self, resource_class: type):
        """
        Decorator to register a scope class.

        Examples:

            @backend.scope(Post)
            class PostScope(BaseScope):
                def resolve(self):
                    if self.user.is_admin(): return self.query
                    return self.query.where(Post.author_id == self.user.id)
        """

        def decorator(scope_class: type["BaseScope"]) -> type["BaseScope"]:
            self.register_scope(resource_class, scope_class)
            return scope_class

        return decorator

    def _get_policy_class(self, resource: Any) -> type[BasePolicy] | None:
        resource_type = type(resource) if resource is not None else type(None)
        for klass in resource_type.__mro__:
            if klass in self._registry:
                return self._registry[klass]
        return self._default_policy

    def get_scope(self, resource_class: type) -> type["BaseScope"] | None:
        for klass in resource_class.__mro__:
            if klass in self._scopes:
                return self._scopes[klass]
        return self._default_scope

    async def authorize(self, user, action: str, resource=None) -> bool:
        policy_class = self._get_policy_class(resource)
        if policy_class is None:
            logger.debug(
                "No policy for resource type %r — denying %r",
                type(resource).__name__,
                action,
            )
            return False

        policy = policy_class(user, resource)
        return policy.can(action)

    async def get_permissions(self, user) -> set[str]:
        # PolicyBackend is resource-scoped; there is no flat permission set.
        # Return empty, callers should use authorize() per-resource.
        return set()

    def registration_defaults(self) -> dict[str, list[str]]:
        return {}

    async def policy_for(self, user, resource) -> BasePolicy | None:
        """
        Return an instantiated policy, or None if no policy is registered.
        """

        cls = self._get_policy_class(resource)
        return cls(user, resource) if cls else None

    async def scope_for(self, user, resource_class: type, query: Any) -> BaseScope | None:
        """
        Return an instantiated scope, or None if no scope is registered.
        """

        cls = self.get_scope(resource_class)
        return cls(user, query) if cls else None
