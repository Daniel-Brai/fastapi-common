import time
from typing import Callable

from fastapi import Request

from lib.ext.fastapi import get_client_ip
from lib.logger import get_logger
from lib.throttler.exceptions import RateLimitExceededError
from lib.throttler.registry import throttler_registry

logger = get_logger("lib.throttler.dependencies")


def _get_client_key(request: Request, key_func: Callable | None = None) -> str:
    """
    Extract the rate-limit key from a request.

    Uses the registry's key_func if set, otherwise the global default from
    configure_throttler, otherwise falls back to get_client_ip.
    """
    if key_func is not None:
        return key_func(request) or "unknown"

    if throttler_registry.is_configured and throttler_registry.key_func is not None:
        return throttler_registry.key_func(request) or "unknown"

    return get_client_ip(request) or "unknown"


async def apply_rate_limit(
    request: Request,
    *,
    limit: str | None = None,
    namespace: str | None = None,
    key_func: Callable | None = None,
) -> None:
    """
    Apply rate limiting imperatively inside a route handler.

    Does nothing if the throttler is not configured or is disabled.
    Raises RateLimitExceeded (HTTP 429) when the limit is exceeded.

    Parameters
    ----------
    request
        The incoming FastAPI Request.
    limit
        Override limit string for this specific call (e.g. "5/minute").
        Falls back to the namespace limit, then the global default.
    namespace
        Override namespace.  Falls back to throttler_registry.namespace.
    key_func
        Override key extraction.  Falls back to the registry's key_func,
        then to utils.request.get_client_ip.

    Raises
    ------
    RateLimitExceeded
        When the rate limit is exceeded.  The exception carries retry_after,
        limit, remaining, reset_at, and a headers dict ready for use in a
        HTTP 429 response.

    Examples
    --------

        ```python
        @router.post("/auth/login")
        async def login(body: LoginBody, request: Request):
            await apply_rate_limit(request, limit="5/minute", namespace="auth:login")
            ...
        ```
    """
    if not throttler_registry.is_configured or not throttler_registry.enabled:
        return

    client_key = _get_client_key(request, key_func)
    rate_namespace = namespace or throttler_registry.namespace

    try:
        allowed = await throttler_registry.hit(
            namespace=rate_namespace,
            client_key=client_key,
            custom_limit=limit,
        )

        if not allowed:
            stats, limit_amount = await throttler_registry.get_window_stats(
                namespace=rate_namespace,
                client_key=client_key,
                custom_limit=limit,
            )
            retry_after = max(1, int(stats.reset_time - time.time()))
            raise RateLimitExceededError(
                retry_after=retry_after,
                limit=limit_amount,
                remaining=max(0, stats.remaining),
                reset_at=stats.reset_time,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit_amount),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(stats.reset_time)),
                },
            )

    except RateLimitExceededError:
        raise
    except Exception:
        logger.warning(
            "Throttler: error checking rate limit for %s/%s — failing open",
            rate_namespace,
            client_key,
            exc_info=True,
        )


def rate_limit(
    limit: str | None = None,
    namespace: str | None = None,
    key_func: Callable | None = None,
) -> Callable:
    """
    FastAPI dependency factory for declarative per-route rate limiting.

    Parameters
    ----------
    limit
        Rate limit string, e.g. "5/minute", "100/hour", "1000/day".
    namespace
        Override namespace.  Defaults to throttler_registry.namespace.
    key_func
        Override key extraction for this route only.

    Returns
    -------
    A FastAPI dependency function (``async def(request: Request) → None``).

    Examples
    --------
        # Attach to a single route
        @router.post("/login", dependencies=[Depends(rate_limit("5/minute"))])
        async def login(body: LoginBody): ...

        # Named namespace — matches namespace_limits config
        @router.post("/upload", dependencies=[Depends(rate_limit("10/hour", namespace="uploads"))])
        async def upload(file: UploadFile): ...

        # Custom key function (rate-limit by user ID instead of IP)
        def user_key(request: Request) -> str:
            return str(request.state.user.id)

        @router.get("/api/data", dependencies=[Depends(rate_limit("100/minute", key_func=user_key))])
        async def get_data(): ...
    """

    async def _dependency(request: Request) -> None:
        await apply_rate_limit(
            request,
            limit=limit,
            namespace=namespace,
            key_func=key_func,
        )

    return _dependency
