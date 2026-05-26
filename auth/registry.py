from lib.auth.authorization import AbstractAuthorizationBackend
from lib.auth.backends import AbstractBackend
from lib.auth.exceptions import AuthConfigError
from lib.auth.helpers.db import is_async_engine
from lib.auth.mailer import AuthMailer
from lib.auth.options import AuthOptions
from lib.auth.providers import AbstractOAuthProvider
from lib.auth.security import Hasher
from lib.auth.types import DBEngine
from lib.auth.user import AuthUserMixin
from lib.logger import get_logger

logger = get_logger("lib.auth.registry")


class AuthRegistry:
    """
    A registry for the auth library's global configuration and shared dependencies.

    Created by configure_auth(). We retrieve the active instance with get_registry().

    Attributes:

        backend (AbstractBackend):  Active authentication backend.
        engine (SQLAlchemy engine): SQLAlchemy engine shared by all DB-touching operations.
        mailer (AuthMailer):   AuthMailer adapter for transactional email flows,
                               the mailer must be configured if using any email-based flows (e.g. password reset, email verification).
        user_model (AuthUserMixin):   Concrete user model class (must subclass AuthUserMixin).
        authorization (AbstractAuthorizationBackend):  Authorization backend (RBAC / PBAC / Policy), or None.
        providers (dict[str, AbstractOAuthProvider]):  Dict of registered OAuth providers keyed by provider name.
        route_prefix (str):  URL prefix under which the auth router is mounted, e.g. "/auth".
                    Used to generate correct redirect/callback URLs for OAuth flows
                    and in the auth router's own prefix when get_auth_router() is called.
    """

    def __init__(
        self,
        backend: AbstractBackend | None = None,
        engine: DBEngine | None = None,
        mailer: AuthMailer | None = None,
        user_model: type[AuthUserMixin] | None = None,
        authorization: AbstractAuthorizationBackend | None = None,
        providers: dict[str, AbstractOAuthProvider] | None = None,
        hasher: Hasher | None = None,
        route_prefix: str = "/auth",
        options: AuthOptions | None = None,
    ):
        self.backend = backend
        self.engine = engine
        self.mailer = mailer
        self.user_model = user_model
        self.authorization = authorization
        self.providers = providers or {}
        self.route_prefix = route_prefix
        self.hasher = hasher
        self.options = options
        self._openapi_scheme = None

    def __repr__(self) -> str:
        return (
            f"AuthRegistry(backend={self.backend}, engine={self.engine}, mailer={self.mailer}, "
            f"user_model={self.user_model}, authorization={self.authorization}, "
            f"providers={list(self.providers.keys())}, route_prefix={self.route_prefix})"
        )

    def configure_auth(
        self,
        backend: AbstractBackend,
        providers: list[AbstractOAuthProvider] | None = None,
        *,
        engine=None,
        mailer: AuthMailer | None = None,
        hasher: Hasher | None = None,
        user_model: type[AuthUserMixin] | None = None,
        authorization: AbstractAuthorizationBackend | None = None,
        route_prefix: str = "/auth",
        options: AuthOptions | None = None,
    ) -> "AuthRegistry":
        """
        Configure the registry with the given parameters.

        Called by the top-level configure_auth() function.
        """

        if not route_prefix.startswith("/"):
            route_prefix = "/" + route_prefix

        route_prefix = route_prefix.rstrip("/")

        self.route_prefix = route_prefix

        self.backend = backend

        if hasher is not None:
            self.hasher = hasher
        else:
            self.hasher = Hasher()

        if options is not None:
            self.options = options
        else:
            self.options = AuthOptions()

        if user_model is not None:
            user_model.__auth_validate__()
            resolved_model = user_model
            self.user_model = resolved_model
        else:
            raise AuthConfigError(
                "Auth: No user_model supplied using built-in SQLModelAuthUser. "
                "Pass user_model=YourUser to customise."
            )

        provider_map: dict[str, AbstractOAuthProvider] = {}
        for p in providers or []:
            provider_map[p.name] = p

        self.providers = provider_map
        self.engine = engine
        self.mailer = mailer
        self.authorization = authorization

        if mailer is None:
            logger.warning(
                "Auth: no mailer configured — forgot-password / magic-link flows "
                "will raise at runtime. Pass mailer= to configure_auth()."
            )
        if authorization is None:
            logger.warning(
                "Auth: no authorization backend — require_permission() and "
                "authorize() will deny all requests. Pass authorization= to configure_auth()."
            )

        return self

    def register_provider(self, provider: AbstractOAuthProvider) -> None:
        """
        Add a provider to this registry.
        Called automatically by configure_auth(providers=[...]) at startup.
        You can also call this after startup to register providers dynamically.
        """

        if provider.name in self.providers:
            return

        self.providers[provider.name] = provider

    def resolve_provider(self, name: str) -> AbstractOAuthProvider:
        """
        Return the provider registered under `name` or raise KeyError.
        """

        if name not in self.providers:
            raise AuthConfigError(
                f"OAuth provider {name!r} is not registered. " "Pass it to configure_auth(providers=[...]) at startup."
            )

        return self.providers[name]

    @property
    def registry(self) -> "AuthRegistry":
        """
        Return the active AuthRegistry instance.  Raises if configure_auth() has not been called.
        """

        if self.backend is None or self.user_model is None or self.engine is None or self.mailer is None:
            raise AuthConfigError("Auth: Registry is not configured. Call configure_auth() at application startup.")

        return self

    @property
    def router_path_prefix(self) -> str:
        """
        Return the URL path prefix under which the auth router is mounted, e.g. "/auth".
        Used to generate correct redirect/callback URLs for OAuth flows.
        """

        return self.route_prefix

    @property
    def auth_options(self) -> AuthOptions:
        if self.options is None:
            raise AuthConfigError("Auth: Options is not configured. Call configure_auth() at application startup.")

        return self.options

    @property
    def auth_backend(self) -> "AbstractBackend":
        if self.backend is None:
            raise AuthConfigError("Auth: Backend is not configured. Call configure_auth() at application startup.")

        return self.backend

    @property
    def user_model_class(self) -> type["AuthUserMixin"]:
        if self.user_model is None:
            raise AuthConfigError("Auth: User model is not configured. Call configure_auth() at application startup.")

        return self.user_model

    @property
    def auth_mailer(self) -> "AuthMailer":
        if self.mailer is None:
            raise AuthConfigError("Auth: Mailer is not configured. Call configure_auth() at application startup.")

        return self.mailer

    @property
    def authorization_backend(self) -> AbstractAuthorizationBackend | None:
        return self.authorization

    @property
    def oauth_providers(self) -> dict[str, AbstractOAuthProvider]:
        return self.providers

    @property
    def db_engine(self) -> DBEngine:
        if self.engine is None:
            raise AuthConfigError("Auth: Engine is not configured. Call configure_auth() at application startup.")

        return self.engine

    @property
    def is_async(self) -> bool:
        return is_async_engine(self.db_engine)

    @property
    def password_hasher(self) -> Hasher:
        if self.hasher is None:
            raise AuthConfigError("Auth: Hasher is not configured. Call configure_auth() at application startup.")

        return self.hasher


auth_registry = AuthRegistry()
