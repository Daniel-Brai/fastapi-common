from .accounts import get_accounts_router
from .email_verification import get_email_verification_router
from .magic_link import get_magic_link_router
from .oauth import oauth_router
from .passwords import get_passwords_router

__all__ = [
    "get_accounts_router",
    "get_email_verification_router",
    "get_magic_link_router",
    "get_passwords_router",
    "oauth_router",
]
