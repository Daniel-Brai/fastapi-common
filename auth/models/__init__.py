"""
SQLModel tables the auth library owns internally.

These are SUPPORT tables.

Your application provides the user model via configure_auth(user_model=User).
See auth/user.py for AuthUserMixin and SQLModelAuthUser.

    `Session`: server-side sessions (SessionBackend)
    `RefreshToken`: persisted refresh tokens (JWTBackend)
    `OAuthAccount`: links an OAuth identity to a user row
    `OneTimeToken`: single-use tokens for password reset, email verification, magic links, and so on.

Foreign keys
────────────
These tables reference users by a generic `user_id` integer column with an
index but NO FK constraint. This keeps them decoupled from whatever
tablename and PK type your user model uses.

If you want a FK constraint, add it manually via an Alembic migration or
SQLModel event listener, or via a trigger after configure_auth() has registered your model.
"""

from .oauth import OAuthAccount
from .ott import OneTimeToken
from .rft import RefreshToken
from .session import Session

__all__ = [
    "OAuthAccount",
    "OneTimeToken",
    "RefreshToken",
    "Session",
]
