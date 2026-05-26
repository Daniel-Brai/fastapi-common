import time
from typing import Callable

from fastapi import Request
from starlette.types import ASGIApp, Scope

from lib.ext.fastapi import get_client_ip
from lib.logger import get_logger
from lib.throttler.config import get_registry
from lib.throttler.exceptions import RateLimitExceededError

logger = get_logger("lib.throttler.middleware")


class ThrottlerMiddleware:
    """
    ASGI-style middleware to apply rate limiting to incoming requests.

    This middleware checks incoming requests against the configured throttler registry and applies rate limits based on client IP or a custom key function.  It can be configured to exclude certain paths or to disable throttling entirely (useful for local development).

    Example usage:

        from fastapi import FastAPI
        from lib.throttler import ThrottlerMiddleware, configure_throttler
        from lib.throttler.storage import RedisStorage

        app = FastAPI()

        configure_throttler(
            storage=RedisStorage("redis://localhost:6379/0"),
            default_limit="100/minute",
            namespace_limits={"auth:login": "10/minute"},
            namespace="api",
        )

        app.add_middleware(ThrottlerMiddleware, exclude_paths=["/health", "/metrics"])
    """

    def __init__(
        self,
        app: ASGIApp,
        namespace: str | None = None,
        custom_limit: str | None = None,
        key_func: Callable[[Request], str] | None = None,
        exclude_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self.registry = get_registry() if get_registry().is_configured else None
        self.namespace = namespace
        self.custom_limit = custom_limit
        self.key_func = key_func
        self.exclude_paths = tuple(exclude_paths or [])

    def _resolve_key(self, request: Request) -> str:
        if self.key_func:
            return self.key_func(request) or "unknown"

        if self.registry and self.registry.key_func:
            return self.registry.key_func(request) or "unknown"

        return get_client_ip(request) or "unknown"

    def _should_skip(self, scope: Scope) -> bool:
        if scope.get("type") != "http":
            return True

        if not self.registry or not self.registry.enabled:
            return True

        if self.exclude_paths:
            path = scope.get("path", "")
            if any(path.startswith(p) for p in self.exclude_paths):
                return True

        return False

    async def __call__(self, scope, receive, send) -> None:

        if self._should_skip(scope):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        client_key = self._resolve_key(request)

        if not self.registry:
            logger.warning("ThrottlerMiddleware: no registry configured, skipping rate limit checks")
            await self.app(scope, receive, send)
            return

        namespace = self.namespace or self.registry.namespace

        try:
            allowed = await self.registry.hit(
                namespace=namespace,
                client_key=client_key,
                custom_limit=self.custom_limit,
            )

            stats, limit_amount = await self.registry.get_window_stats(
                namespace=namespace,
                client_key=client_key,
                custom_limit=self.custom_limit,
            )

            if not allowed:
                retry_after = max(1, int(stats.reset_time - time.time()))

                raise RateLimitExceededError(
                    retry_after=retry_after,
                    limit=limit_amount,
                    remaining=max(0, stats.remaining),
                    reset_at=stats.reset_time,
                )

        except RateLimitExceededError as re:
            raise re
        except Exception:
            logger.warning(
                "ThrottlerMiddleware: unexpected error for %s/%s — failing open",
                namespace,
                client_key,
                exc_info=True,
            )
            await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
