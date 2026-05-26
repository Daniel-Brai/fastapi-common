from typing import Callable

from fastapi import APIRouter

from lib.auth.config import get_auth_router_prefix, get_oauth_providers, get_options
from lib.auth.routers import (
    get_accounts_router,
    get_email_verification_router,
    get_magic_link_router,
    get_passwords_router,
    oauth_router,
)


def get_auth_router(auth_dep: Callable, tag: str = "Authentication") -> APIRouter:
    """
    Mount this in your app to get all the auth routes

    Parameters:
        tag:
            OpenAPI tag for the routes in this router. Default: "Authentication".

    Examples:

        from auth import get_auth_router
        app.include_router(get_auth_router())
        # /auth/login, /auth/register, /auth/oauth/google/redirect

    The prefix is normalised in configure_auth() so it always starts with
    a leading slash and has no trailing slash.
    """

    prefix = get_auth_router_prefix()
    options = get_options()
    oauth_providers = get_oauth_providers()

    auth_router = APIRouter(prefix=prefix, tags=[tag])
    auth_router.include_router(get_passwords_router(options))
    auth_router.include_router(get_email_verification_router(options))
    auth_router.include_router(get_accounts_router(auth_dep, options))

    magic_link_router = get_magic_link_router(options)

    if magic_link_router:
        auth_router.include_router(magic_link_router)

    if oauth_providers:
        auth_router.include_router(oauth_router)

    return auth_router
