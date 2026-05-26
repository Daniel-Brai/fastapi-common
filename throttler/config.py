from typing import Callable

from limits.aio.strategies import RateLimiter

from lib.throttler.registry import ThrottlerRegistry, throttler_registry
from lib.throttler.storage import MemoryStorage, RedisStorage


def configure_throttler(
    storage: MemoryStorage | RedisStorage,
    strategy_cls: type[RateLimiter] | None = None,
    *,
    default_limit: str = "100/minute",
    namespace_limits: dict[str, str] | None = None,
    namespace: str = "api",
    enabled: bool = True,
    key_func: Callable | None = None,
) -> ThrottlerRegistry:
    """
    Set configuration and initialise the rate limiter storage.

    Safe to call multiple times — re-configuring tears down cached
    limiters and rebuilds storage from the new backend.

    Parameters
    ----------
    storage
        A MemoryStorage or RedisStorage instance.  Pass MemoryStorage()
        for local/dev and RedisStorage(url) for staging/production.
    strategy_cls
        Optional custom RateLimiter strategy class.  Must be compatible with the storage backend.  Default is limits.aio.strategies.FixedWindowRateLimiter.
    default_limit
        Rate limit applied to all namespaces unless overridden.
        Format: "<count>/<period>".  Periods: second, minute, hour, day.
    namespace_limits
        Per-namespace limit overrides.  Keys are namespace strings.
        Merged with default_limit at hit() time.
    namespace
        Default namespace for apply_rate_limit() / the middleware when
        no explicit namespace is given.
    enabled
        Set to False to disable all rate limit checks (good for local dev
        and tests).  Middleware and dependencies still run but always pass.
    key_func
        Optional callable(Request) → str to extract the rate-limit key.
        Default: extracts client IP via utils.request.get_client_ip.


    Examples
    --------
    Local development (no limits):

        configure_throttler(storage=MemoryStorage(), enabled=False)

    Production with per-route overrides:

        configure_throttler(
            storage          = RedisStorage(settings.REDIS_URL),
            default_limit    = "200/minute",
            namespace_limits = {
                "auth:login":           "10/minute",
                "auth:forgot-password": "5/hour",
                "api:search":           "60/minute",
            },
            namespace = "api",
        )
    """

    return throttler_registry.configure_throttler(
        storage,
        strategy_cls,
        default_limit=default_limit,
        namespace_limits=namespace_limits,
        namespace=namespace,
        enabled=enabled,
        key_func=key_func,
    )


def is_throttler_configured() -> bool:
    """
    Return True if the throttler has been configured.

    This can be used to check if configure_throttler() has been called before
    attempting to get the registry or apply rate limits.
    """
    return throttler_registry.is_configured


def get_registry() -> ThrottlerRegistry:
    """
    Return the singleton ThrottlerRegistry.

    Raises ThrottlerNotConfigured if configure_throttler() has not been called.
    """
    throttler_registry.assert_configured()

    return throttler_registry
