import time
from typing import Any, Callable, MutableMapping

from starlette.types import ASGIApp, Receive, Scope, Send


class RequestTimingMiddleware:
    """
    ASGI-style middleware for `X-Process-Time` header.

    Parameters:
        app (ASGIApp): The ASGI application to wrap.
        header_name (str): The name of the header to add with the processing time. Default is "X-Process-Time".
        before_request (Callable[[Scope], None] | None): Optional callable executed before the request is forwarded.
        after_request (Callable[[Scope, int | None, float], None] | None): Optional callable executed after a successful response.
        on_error (Callable[[Scope, Exception, float], None] | None): Optional callable executed when the request raises an exception.

    Usage:

        from fastapi import FastAPI
        from middlewares.request_timing import RequestTimingMiddleware

        app = FastAPI()
        app.add_middleware(
            RequestTimingMiddleware,
            header_name="X-Process-Time",
            before_request=lambda scope: ...,
            after_request=lambda scope, status, duration: ...,
            on_error=lambda scope, exc, duration: ...,
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        header_name: str = "X-Process-Time",
        before_request: Callable[[Scope], None] | None = None,
        after_request: Callable[[Scope, int | None, float], None] | None = None,
        on_error: Callable[[Scope, Exception, float], None] | None = None,
    ) -> None:
        self.app = app
        self.header_name = header_name
        self.before_request = before_request
        self.after_request = after_request
        self.on_error = on_error

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.before_request is not None:
            self.before_request(scope)

        start_time = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0))
                duration = time.perf_counter() - start_time
                headers = list(message.get("headers", []))
                headers.append((self.header_name.encode(), str(duration).encode()))
                message["headers"] = headers

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            duration = time.perf_counter() - start_time
            if self.on_error is not None:
                self.on_error(scope, e, duration)
            raise
        else:
            duration = time.perf_counter() - start_time
            if self.after_request is not None:
                self.after_request(scope, status_code, duration)
