from base64 import b64encode
from hashlib import md5
from typing import NoReturn

from starlette.datastructures import Headers, MutableHeaders
from starlette.status import HTTP_200_OK, HTTP_304_NOT_MODIFIED
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ETagMiddleware:
    """
    ASGI middleware that adds ETag headers to GET responses and handles If-None-Match requests.

    Parameters
    ----------
    minimum_size (int)
        Minimum response body size in bytes to calculate and add an ETag header.  Default 80 bytes.
    exclude_paths (set[str] | None)
        Optional set of URL paths to exclude from ETag processing.  Default None (process all paths).

    Example:

        # with default settings
        app = FastAPI()
        app.add_middleware(ETagMiddleware)

        # with custom settings
        app.add_middleware(ETagMiddleware, minimum_size=100, exclude_paths={"/health"})
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 80,
        exclude_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.exclude_paths = exclude_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "GET" and not self._is_excluded_path(scope["path"]):
            responder = ETagResponder(self.app, scope, self.minimum_size)
            await responder(scope, receive, send)
        else:
            await self.app(scope, receive, send)

    def _is_excluded_path(self, path: str) -> bool:
        if self.exclude_paths is None:
            return False

        for excluded in self.exclude_paths:
            if path == excluded:
                return True

            if excluded.endswith("/"):
                if path.startswith(excluded):
                    return True
            elif path.startswith(excluded + "/"):
                return True

        return False


class ETagResponder:
    def __init__(self, app: ASGIApp, scope: Scope, minimum_size: int) -> None:
        self.app = app
        self.scope = scope
        self.minimum_size = minimum_size
        self.send: Send = unattached_send
        self.initial_message: Message = {}
        self.headers: MutableHeaders | None = None
        self.status_code: int | None = None
        self.delay_sending: bool = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.send_with_etag)

    async def send_with_etag(self, message: Message) -> None:
        if self.status_code is None:
            self.status_code = message.get("status")

        if self.status_code != HTTP_200_OK:
            if self.status_code != HTTP_304_NOT_MODIFIED:
                await self.send(message)
            elif message.get("type") == "http.response.start":
                await self.send(message)
                await self.send({"type": "http.response.body", "body": b"", "more_body": False})

            return

        message_type = message["type"]
        if message_type == "http.response.start":
            self.headers = MutableHeaders(raw=message["headers"])
            etag = self.headers.get("etag")
            if etag:
                if self.compare_etag_with_if_none_match(etag):
                    self.status_code = message["status"] = HTTP_304_NOT_MODIFIED
                    del self.headers["content-length"]
                    await self.send(message)
                    await self.send({"type": "http.response.body", "body": b"", "more_body": False})
                    return
            else:
                content_length = self.headers.get("content-length")
                if content_length:
                    size = int(content_length)
                    if size >= self.minimum_size:
                        self.initial_message = message
                        return

            self.delay_sending = False

            await self.send(message)
        elif message_type == "http.response.body":
            if not self.delay_sending:
                await self.send(message)
                return

            assert not message.get("more_body", False)

            body = message.get("body", b"")
            if len(body) >= self.minimum_size:
                etag = f'''"{b64encode(md5(body).digest())[:-2].decode('ascii')}"'''
                assert self.headers is not None
                self.headers["etag"] = etag

                if self.compare_etag_with_if_none_match(etag):
                    del self.headers["content-length"]
                    self.initial_message["status"] = HTTP_304_NOT_MODIFIED
                    message["body"] = b""

            await self.send(self.initial_message)

            await self.send(message)

    def compare_etag_with_if_none_match(self, etag: str) -> bool:
        if_none_match = Headers(scope=self.scope).get("if-none-match")
        if if_none_match:
            if if_none_match[:2] == "W/":
                if_none_match = if_none_match[2:]
            return if_none_match == etag
        return False


async def unattached_send(message: Message) -> NoReturn:  # noqa: ARG001
    raise RuntimeError("send awaitable not set")  # pragma: no cover
