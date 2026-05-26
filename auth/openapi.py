from typing import Any

from fastapi.security import APIKeyCookie, HTTPBearer

from lib.auth.backends.base import AbstractBackend


def make_openapi_scheme(backend: AbstractBackend) -> Any:
    """
    Makes the appropriate OpenAPI security scheme based on the configured auth backend.
    """

    if backend.name == "jwt":
        return HTTPBearer(auto_error=False)

    elif backend.name == "session":
        cookie_name = getattr(backend, "cookie_name", "session_id")
        return APIKeyCookie(
            name=cookie_name,
            scheme_name=cookie_name,
            auto_error=False,
        )

    # Default to HTTP Bearer for unknown backends
    return HTTPBearer(auto_error=False)
