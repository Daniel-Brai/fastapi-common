from .authorization import AbstractAuthorizationBackend, BasePolicy, BaseScope, PBACBackend, PolicyBackend, RBACBackend
from .backends import JWTBackend, SessionBackend
from .config import (
    configure_auth,
    get_auth_router_prefix,
    get_authorization,
    get_backend,
    get_engine,
    get_hasher,
    get_mailer,
    get_registry,
    get_user_model,
)
from .dependencies import authorize, make_auth_dependency, require_any_permission, require_permission, require_roles
from .exceptions import (
    AuthConfigError,
    AuthError,
    EmailAlreadyVerified,
    EmailNotVerified,
    InactiveUser,
    InvalidCredentials,
    NotAuthenticated,
    OAuthError,
    OAuthStateMismatch,
    PermissionDenied,
    RefreshTokenReuse,
    TokenExpired,
    TokenInvalid,
    TokenRevoked,
)
from .helpers import create_user, create_users
from .jobs import ScheduleAccountDeletionJob, SendAuthEmailJob, SweepAuthJob
from .mailer import AuthMailer
from .models import OAuthAccount, OneTimeToken, RefreshToken, Session
from .options import AuthOptions
from .providers import AppleProvider, GitHubProvider, GoogleProvider
from .registry import AuthRegistry
from .router import get_auth_router
from .security import Hasher
from .throttler import AUTH_THROTTLER_LIMITS
from .token import AccessTokenClaims, RefreshTokenClaims, TokenCodec, TokenPair
from .user import AuthUserMixin, SQLModelAuthUser

__all__ = [
    "AuthRegistry",
    "configure_auth",
    "get_registry",
    "get_backend",
    "get_engine",
    "get_mailer",
    "get_user_model",
    "get_authorization",
    "Hasher",
    "AuthUserMixin",
    "SQLModelAuthUser",
    "AbstractAuthorizationBackend",
    "RBACBackend",
    "PBACBackend",
    "BasePolicy",
    "PolicyBackend",
    "BaseScope",
    "SessionBackend",
    "JWTBackend",
    "GoogleProvider",
    "AppleProvider",
    "GitHubProvider",
    "Session",
    "RefreshToken",
    "OAuthAccount",
    "AuthOptions",
    "AUTH_THROTTLER_LIMITS",
    "OneTimeToken",
    "TokenCodec",
    "TokenPair",
    "AccessTokenClaims",
    "RefreshTokenClaims",
    "AuthMailer",
    "create_user",
    "create_users",
    "AuthError",
    "NotAuthenticated",
    "InvalidCredentials",
    "TokenExpired",
    "TokenInvalid",
    "TokenRevoked",
    "RefreshTokenReuse",
    "InactiveUser",
    "PermissionDenied",
    "OAuthError",
    "OAuthStateMismatch",
    "EmailNotVerified",
    "EmailAlreadyVerified",
    "AuthConfigError",
    "AuthRegistry",
    "make_auth_dependency",
    "configure_auth",
    "get_registry",
    "get_backend",
    "get_engine",
    "get_mailer",
    "get_user_model",
    "get_authorization",
    "get_hasher",
    "get_auth_router_prefix",
    "require_roles",
    "require_permission",
    "require_any_permission",
    "authorize",
    "get_auth_router",
    "SendAuthEmailJob",
    "SweepAuthJob",
    "ScheduleAccountDeletionJob",
]
