import time
from typing import Any, MutableMapping

from starlette.types import ASGIApp, Receive, Scope, Send

from .logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    """
    ASGI-style middleware to log HTTP requests.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        query_string = scope.get("query_string", b"").decode("utf-8")
        full_path = f"{path}?{query_string}" if query_string else path

        start_time = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0))

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                method=method,
                path=full_path,
                duration_ms=round(duration_ms, 2),
                error=str(e),
                exc_info=e,
            )
            raise e

        duration_ms = (time.perf_counter() - start_time) * 1000
        log_method = logger.info if status_code and 200 <= status_code < 400 else logger.warning
        log_method(
            "request_completed",
            method=method,
            path=full_path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
        )
