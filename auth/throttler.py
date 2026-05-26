from typing import Any, Literal

from fastapi import Depends

from lib.auth.options import AuthOptions

AUTH_THROTTLER_LIMITS = {
    "auth:accounts:login": "5/minute",
    "auth:accounts:register": "3/minute",
    "auth:accounts:refresh": "10/minute",
    "auth:accounts:logout": "10/minute",
    "auth:accounts:me": "60/minute",
    "auth:accounts:change_password": "5/minute",
    "auth:accounts:change_email": "5/minute",
    "auth:passwords:forgot_password": "3/minute",
    "auth:passwords:reset_password": "3/minute",
    "auth:email_verification:send_verification_email": "5/minute",
    "auth:email_verification:verify_email": "5/minute",
    "auth:magic_links:accounts:request_magic_link": "3/minute",
    "auth:magic_links:accounts:consume_magic_link": "5/minute",
}


def get_throttler_for_router(
    options: AuthOptions,
    name: Literal["accounts", "passwords", "email_verification", "magic_link"],
) -> dict[str, list[Any]]:
    """
    Get a list of dependencies for throttling all endpoints in a router.

    This is used to apply the same throttler to all endpoints in a router, e.g. all account-related endpoints.

    If the throttler is disabled in AuthOptions, returns an empty list.
    """
    from lib.throttler.dependencies import rate_limit

    if not options.throttler_enabled:
        return {}

    dependencies = {}
    for endpoint in AUTH_THROTTLER_LIMITS:
        if endpoint.startswith(f"auth:{name}"):
            endpoint_name = endpoint.split(":")[-1]
            dependencies[endpoint_name] = [Depends(rate_limit(AUTH_THROTTLER_LIMITS[endpoint], namespace=endpoint))]

    return dependencies
