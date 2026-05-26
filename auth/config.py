from typing import Any

from lib.auth.authorization import AbstractAuthorizationBackend
from lib.auth.backends import AbstractBackend
from lib.auth.mailer import AuthMailer
from lib.auth.options import AuthOptions
from lib.auth.providers import AbstractOAuthProvider
from lib.auth.registry import AuthRegistry, auth_registry
from lib.auth.security import Hasher
from lib.auth.types import DBEngine
from lib.auth.user import AuthUserMixin


def configure_auth(
    backend: AbstractBackend,
    providers: list[AbstractOAuthProvider] | None = None,
    *,
    engine: DBEngine,
    mailer: AuthMailer | None = None,
    hasher: Hasher | None = None,
    user_model: type[AuthUserMixin] | None = None,
    authorization: AbstractAuthorizationBackend | None = None,
    auth_route_prefix: str = "/auth",
    options: AuthOptions | None = None,
) -> AuthRegistry:
    """
    Configure your authentication service

    Call once before your application starts

    Parameters
    ----------
    backend (AbstractBackend)
        Authentication backend: SessionBackend or JWTBackend.
        Do NOT pass an engine to the backend constructor; use the engine=
        argument here instead.
    providers (list[AbstractOAuthProvider] | None)
        OAuth providers to register (GoogleProvider, AppleProvider, …).
        You can implement your own by subclassing AbstractOAuthProvider and implementing the required methods.
    engine (DBEngine)
        SQLAlchemy engine shared by all DB operations in the auth library.
        Backends, flows, and one-time-token helpers all read this.
    mailer (AuthMailer | None)
        AuthMailer adapter for forgot-password / verification / magic-link flows.
    user_model (type[AuthUserMixin] | None)
        Concrete user model class.  Must subclass AuthUserMixin and declare all
        required fields including password_salt.
        Defaults to the built-in SQLModelAuthUser when omitted.
    hasher (Hasher | None)
        Hasher instance to use for password hashing and verification.
        Defaults to the built-in Hasher with argon2id and secure defaults when omitted.
        To configure it, use `Hasher.configure(time_cost=..., memory_cost=..., parallelism=...)` at application startup.
    authorization (AbstractAuthorizationBackend | None)
        Authorization backend: RBACBackend, PBACBackend, or PolicyBackend.
    auth_route_prefix (str)
        URL prefix the auth router will be mounted under.  Default "/auth".
        Use get_auth_router() to obtain a pre-configured APIRouter that
        already has this prefix applied, so you can do:

            app.include_router(get_auth_router(auth_dep=auth_dep))
            #  /auth/login, /auth/register, /auth/oauth/google/redirect,
            #  /auth/forgot-password, etc.
    options (AuthOptions)
        Additional options for configuring form behavior, token lifetimes, etc.

    Examples
    --------
    JWT + RBAC:

        configure_auth(
            JWTBackend(codec=TokenCodec(secret=settings.JWT_SECRET)),
            user_model    = User,
            authorization = RBACBackend(
                {
                    "superadmin": ["*"],
                    "admin":      ["users:read", "users:write", "posts:*"],
                    "editor":     ["posts:create", "posts:edit", "posts:read"],
                    "viewer":     ["posts:read"],
                },
                default_roles=["viewer"],
            ),
            engine       = engine,
            mailer       = AuthMailer(base_url="https://yourapp.com"),
            route_prefix = "/auth",
        )

    JWT + PBAC:

        configure_auth(
            JWTBackend(codec=TokenCodec(secret=settings.JWT_SECRET)),
            user_model    = User,
            authorization = PBACBackend(
                role_permissions={
                    "admin":  ["*"],
                    "editor": ["posts:create", "posts:edit", "posts:read"],
                },
                default_roles=["editor"],
                default_permissions=["comments:read"],
            ),
            engine       = engine,
            mailer       = AuthMailer(base_url="https://yourapp.com"),
            route_prefix = "/auth",
        )

    Session + Policies:

        configure_auth(
            SessionBackend(secret_key=settings.SECRET_KEY),
            user_model    = User,
            authorization = policies,
            engine        = engine,
            mailer        = AuthMailer(base_url="https://yourapp.com"),
            route_prefix  = "/api/v1/auth",
        )
    """

    return auth_registry.configure_auth(
        backend=backend,
        providers=providers,
        engine=engine,
        mailer=mailer,
        hasher=hasher,
        user_model=user_model,
        authorization=authorization,
        route_prefix=auth_route_prefix,
        options=options,
    )


def get_registry() -> AuthRegistry:
    """
    Return the active AuthRegistry singleton configured via configure_auth().
    """
    return auth_registry.registry


def get_options() -> AuthOptions:
    """
    Return the active AuthOptions instance configured via configure_auth(options=...).
    """
    return get_registry().auth_options


def get_backend() -> AbstractBackend:
    """
    Return the active authentication backend configured via configure_auth(backend=...).
    """
    return get_registry().auth_backend


def get_engine() -> DBEngine:
    """
    Return the SQLAlchemy engine shared by all DB operations in the auth library.
    """
    return get_registry().db_engine


def get_mailer() -> "AuthMailer":
    """
    Return the active AuthMailer instance configured via configure_auth(mailer=...).
    """
    return get_registry().auth_mailer


def get_user_model() -> type[AuthUserMixin]:
    """
    Return the active user model class configured via configure_auth(user_model=...).
    """
    return get_registry().user_model_class


def get_authorization() -> AbstractAuthorizationBackend | None:
    """
    Return the active authorization backend configured via configure_auth(authorization=...).
    """
    return get_registry().authorization_backend


def get_hasher() -> Hasher:
    """
    Return the active Hasher instance configured via configure_auth(hasher=...).
    """
    return get_registry().password_hasher


def register_provider(provider: "AbstractOAuthProvider") -> None:
    """
    Add a provider to the active AuthRegistry.
    """

    get_registry().register_provider(provider)


def resolve_provider(name: str) -> "AbstractOAuthProvider":
    """
    Return the provider registered under `name` or raise AuthConfigError.
    """

    return get_registry().resolve_provider(name)


def get_oauth_providers() -> dict[str, "AbstractOAuthProvider"]:
    """
    Return a snapshot dict of all registered providers or raise AuthConfigError if no providers registered.
    """

    return get_registry().oauth_providers


def get_auth_router_prefix() -> str:
    """
    Return the URL path prefix under which the auth router is mounted, e.g. "/auth".
    Used to generate correct redirect/callback URLs for OAuth flows.
    """
    return get_registry().router_path_prefix


def get_authorization_defaults(
    user_model: type[AuthUserMixin] | None = None,
) -> dict[str, Any]:
    """
    Return backend-provided defaults to apply when creating new users.

    Only keys that exist on the resolved user model are returned.
    """

    authorization = get_authorization()
    if authorization is None:
        return {}

    defaults_fn = getattr(authorization, "registration_defaults", None)
    raw_defaults = defaults_fn() if callable(defaults_fn) else {}
    defaults = raw_defaults if isinstance(raw_defaults, dict) else {}
    resolved_model = user_model or get_user_model()

    allowed_fields: set[str] = set()
    model_fields = getattr(resolved_model, "model_fields", None)
    if isinstance(model_fields, dict):
        allowed_fields.update(str(name) for name in model_fields.keys())

    for klass in reversed(resolved_model.__mro__):
        allowed_fields.update(getattr(klass, "__annotations__", {}).keys())

    safe_defaults: dict[str, Any] = {}
    for key, value in defaults.items():
        if key not in allowed_fields:
            continue

        if isinstance(value, list):
            safe_defaults[key] = list(value)
        elif isinstance(value, dict):
            safe_defaults[key] = dict(value)
        elif isinstance(value, set):
            safe_defaults[key] = set(value)
        else:
            safe_defaults[key] = value

    return safe_defaults
