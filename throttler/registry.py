from typing import Any, Callable

from limits.aio.strategies import RateLimiter

from lib.throttler.exceptions import ThrottlerNotConfiguredError


class ThrottlerRegistry:
    """
    Singleton that owns all throttler runtime configuration.

    Instantiated once at module import time as ``throttler_registry``.
    Configured via ``throttler_registry.configure_throttler(...)`` or the
    module-level ``configure_throttler(...)`` shortcut.

    Attributes
    ----------
    storage_backend
        A MemoryStorage or RedisStorage instance describing which backing
        store to use.
    default_limit
        Default rate limit string applied to all namespaces unless overridden.
        Format: "<count>/<period>" where period is second, minute, hour, or day.
        Examples: "100/minute", "1000/hour", "10/second"
    namespace_limits
        Per-namespace overrides.  Keys are namespace strings; values are
        limit strings.  Takes priority over default_limit.
        Example: {"auth:login": "5/minute", "api:upload": "10/hour"}
    namespace
        Default namespace used by apply_rate_limit() when none is specified.
        Default: "api"
    enabled
        When False, all rate limit checks are skipped (no storage lookups).
        Useful in local/test environments.  Default: True.
    key_func
        Callable(Request) → str.  Extracts the rate-limit key from a request.
        Default: get_client_ip(request) from utils.request.
    """

    def __init__(self) -> None:
        self._configured: bool = False
        self.storage_backend: Any = None
        self.strategy_cls: type[RateLimiter] | None = None
        self._storage: Any = None  # built lazily
        self._limiters: dict[str, Any] = {}
        self.default_limit: str = "100/minute"
        self.namespace_limits: dict[str, str] = {}
        self.namespace: str = "api"
        self.enabled: bool = True
        self.key_func: Callable | None = None

    def configure_throttler(
        self,
        storage,
        strategy_cls: type[RateLimiter] | None = None,
        *,
        default_limit: str = "100/minute",
        namespace_limits: dict[str, str] | None = None,
        namespace: str = "api",
        enabled: bool = True,
        key_func: Callable | None = None,
    ) -> "ThrottlerRegistry":
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

        Returns
        -------
        self — the singleton, for chaining.

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
        self.storage_backend = storage
        self.strategy_cls = strategy_cls
        self.default_limit = default_limit
        self.namespace_limits = namespace_limits or {}
        self.namespace = namespace
        self.enabled = enabled
        self.key_func = key_func
        self._configured = True

        # Tear down cached limiters when storage may have changed
        self._limiters = {}
        self._storage = None  # rebuilt lazily on first hit

        return self

    @property
    def is_configured(self) -> bool:
        return self._configured

    def assert_configured(self) -> None:
        if not self._configured:
            from .exceptions import ThrottlerNotConfiguredError

            raise ThrottlerNotConfiguredError()

    def __repr__(self) -> str:  # pragma: no cover
        if not self._configured:
            return "ThrottlerRegistry(unconfigured)"
        return (
            f"ThrottlerRegistry("
            f"storage={self.storage_backend!r}, "
            f"default={self.default_limit!r}, "
            f"enabled={self.enabled})"
        )

    def _get_storage(self):
        """Build (or return cached) async storage from the configured backend."""
        if self._storage is None:
            if self.storage_backend is None:
                raise ThrottlerNotConfiguredError(
                    "No storage backend configured. Pass storage= to configure_throttler()."
                )
            self._storage = self.storage_backend.build()
        return self._storage

    def _get_limiter(self, namespace: str):
        """
        Return (or create) a RateLimiter strategy for the given namespace.
        """
        if namespace not in self._limiters:
            from limits.aio.strategies import MovingWindowRateLimiter

            strategy = self.strategy_cls or MovingWindowRateLimiter

            self._limiters[namespace] = strategy(self._get_storage())

        return self._limiters[namespace]

    def _resolve_limit(self, namespace: str, custom_limit: str | None = None):
        """Return the parsed RateLimitItem for this namespace."""
        from limits import parse

        limit_str = custom_limit or self.namespace_limits.get(namespace, self.default_limit)
        return parse(limit_str)

    async def hit(
        self,
        namespace: str,
        client_key: str,
        custom_limit: str | None = None,
    ) -> bool:
        """
        Record a hit and return True if allowed, False if the limit is exceeded.

        Parameters
        ----------
        namespace
            Logical group for this limit (e.g. "auth:login", "api:search").
        client_key
            Per-client identifier — typically the IP address.
        custom_limit
            Override the namespace limit just for this call.

        Returns True when the request is within the rate limit.
        """

        self.assert_configured()

        if not self.enabled:
            return True

        limiter = self._get_limiter(namespace)
        limit_item = self._resolve_limit(namespace, custom_limit)
        key = f"{namespace}:{client_key}"
        return await limiter.hit(limit_item, key)

    async def get_window_stats(
        self,
        namespace: str,
        client_key: str,
        custom_limit: str | None = None,
    ):
        """
        Return (WindowStats, limit_amount) for a namespace+client_key.

        WindowStats has:
            .remaining  — requests remaining in the current window
            .reset_time — Unix timestamp when the window resets

        Use after a failed hit() to populate response headers.
        """

        self.assert_configured()

        limiter = self._get_limiter(namespace)
        limit_item = self._resolve_limit(namespace, custom_limit)
        key = f"{namespace}:{client_key}"
        stats = await limiter.get_window_stats(limit_item, key)

        return stats, limit_item.amount

    async def clear(self, namespace: str, client_key: str) -> None:
        """
        Clear the rate limit counter for a specific namespace + client key.

        Useful after a successful authentication to reset login attempt counts.

            await throttler_registry.clear("auth:login", user_ip)
        """
        self.assert_configured()

        if not self.enabled:
            return

        limiter = self._get_limiter(namespace)
        limit_item = self._resolve_limit(namespace)
        key = f"{namespace}:{client_key}"
        await limiter.clear(limit_item, key)


throttler_registry: ThrottlerRegistry = ThrottlerRegistry()
