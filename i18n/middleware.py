from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

if TYPE_CHECKING:
    from .base import I18n


class I18nMiddleware:
    """
    Pure ASGI middleware that detects the request locale and binds it to
    the current async context.

    Parameters
    ----------
    app:
        The ASGI application (passed automatically by Starlette/FastAPI).
    i18n:
        Your configured :class:`~lib.i18n.base.I18n` instance.
    expose_locale_header:
        If ``True``, add an ``X-Locale`` response header with the resolved
        locale so clients can confirm which locale was selected.
    locale_header_name:
        The name of the response header to use when ``expose_locale_header`` is
        ``True``.  Defaults to ``X-Locale``.
    locale_cookie_name:
        The name of the cookie to check for locale preferences.  Defaults to
        ``locale``.

    Registration::

        app.add_middleware(I18nMiddleware, i18n=i18n)
        app.add_middleware(I18nMiddleware, i18n=i18n, expose_locale_header=True)
    """

    def __init__(
        self,
        app: ASGIApp,
        i18n: "I18n",
        expose_locale_header: bool = False,
        locale_header_name: str = "X-Locale",
        locale_cookie_name: str = "locale",
    ) -> None:
        self.app = app
        self._i18n = i18n
        self._expose_header = expose_locale_header
        self._header_name = locale_header_name
        self._cookie_name = locale_cookie_name

        if not i18n._negotiators:
            i18n.add_negotiator(_negotiate_from_query)
            i18n.add_negotiator(lambda request: _negotiate_from_cookie(request, self._cookie_name))
            i18n.add_negotiator(_negotiate_from_header)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        locale = self._i18n.negotiate_locale(request)
        token = self._i18n.set_locale(locale)

        try:
            if self._expose_header:
                await self.app(scope, receive, _make_send_wrapper(send, locale, self._header_name))
            else:
                await self.app(scope, receive, send)
        finally:
            self._i18n.reset_locale(token)


def _make_send_wrapper(send: Send, locale: str, header_name: str) -> Send:
    """
    Return a wrapped ``send`` callable that injects ``X-Locale: <locale>``
    into the ``http.response.start`` ASGI message.
    """

    async def send_wrapper(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers: list = list(message.get("headers", []))
            headers.append((header_name.lower().encode("latin-1"), locale.encode("latin-1")))
            message = {**message, "headers": headers}

        await send(message)

    return send_wrapper


def _negotiate_from_query(request: Request) -> str | None:
    """
    Check the ``?lang=`` query parameter.

    Example: ``GET /hello?lang=fr``
    """
    return request.query_params.get("lang")


def _negotiate_from_header(request: Request) -> str | None:
    """
    Parse the ``Accept-Language`` HTTP header (RFC 7231).

    Returns the highest-priority language tag (ignoring ``q`` weights below
    the top entry).  Example::

        Accept-Language: fr-CH, fr;q=0.9, en;q=0.8  →  "fr-CH"
    """
    accept = request.headers.get("Accept-Language", "")
    if not accept:
        return None

    languages: list[tuple[str, float]] = []
    for part in accept.split(","):
        tag, *rest = part.strip().split(";")
        q = 1.0
        for segment in rest:
            segment = segment.strip()
            if segment.startswith("q="):
                try:
                    q = float(segment[2:])
                except ValueError:
                    pass

        languages.append((tag.strip(), q))

    languages.sort(key=lambda x: x[1], reverse=True)
    return languages[0][0] if languages else None


def _negotiate_from_cookie(request: Request, cookie_name: str = "locale") -> str | None:
    """
    Check the ``locale`` cookie.

    Example: ``Cookie: locale=de``
    """
    return request.cookies.get(cookie_name)
