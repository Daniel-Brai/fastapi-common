from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lib.monitoring.database.detector import DetectorConfig, N1Detector
from lib.monitoring.database.tracker import clear_request_log, start_request_log


class MonitorMiddleware:
    """
    Middleware for N+1 detection around every HTTP request

    Usage::

        from fastapi import FastAPI
        from lib.database import MonitorMiddleware, DetectorConfig, instrument_monitoring

        engine = create_engine(DATABASE_URL)
        instrument_monitoring(engine)

        app = FastAPI()
        app.add_middleware(
            MonitorMiddleware,
            config=DetectorConfig(threshold=3),
            add_response_header=True,
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        config: DetectorConfig | None = None,
        add_response_header: bool = False,
        enabled: bool = True,
    ) -> None:
        self.app = app
        self.detector = N1Detector(config or DetectorConfig())
        self.add_response_header = add_response_header
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        log = start_request_log()
        try:
            await self.app(scope, receive, self._make_send(send, log))
        finally:
            self.detector.analyse(log)
            clear_request_log()

    def _make_send(self, send: Send, log) -> Send:  # type: ignore[override]
        """
        Wrap *send* so we can inject headers into the ``http.response.start``
        message without touching or buffering the body at all.
        """
        middleware = self

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and middleware.add_response_header:
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.append((b"x-db-queries", str(log.count).encode()))

                message = {**message, "headers": headers}

            await send(message)

        return send_wrapper
