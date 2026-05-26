from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lib.logger import get_logger

logger = get_logger("lib.ext.fastapi.middlewares.error_page")


class ErrorPageMiddleware:
    """
    ASGI middleware that intercepts responses with specified error status codes
    and renders a raw static HTML error page.

    It interpolates standard placeholders in the provided template: `{{ status_code }}`,
    `{{ title }}`, `{{ error_message }}`, `{{ action_button }}`, and `{{ favicon_url }}`.

    The `{{ action_button }}` is dynamically rendered as a "Go Back" button if the user
    navigated from within the same origin, or a "Back to Home" link otherwise (with a
    JavaScript fallback).

    If a `translator` callable is provided, the middleware will attempt to translate
    the text placeholders using these specific translation keys:
    - `"seo.error.title"` (passed with kwarg `status_code=...`)
    - `"page.title"` (fallback for title if `"seo.error.title"` is not found)
    - `"page.status_404"`, `"page.status_500"`, etc. (for the error message)
    - `"page.back_to_home"` (for the "Back to Home" link text)
    - `"page.go_back"` (for the "Go Back" button text)

    Args:
        app (ASGIApp): The next ASGI application or middleware in the stack.
        favicon_url (str | None, optional): URL for the favicon to inject into the
            HTML template. Defaults to None (falls back to "/favicon.ico").
        template_path (Path | str, optional): Path to the raw HTML template. If a
            relative path is provided, it resolves relative to this file's directory.
            Defaults to "error.html".
        translator (Any | None, optional): A callable (e.g., from an i18n system) that
            takes a translation key and returns a translated string. Expected to handle
            keys like `seo.error.title`, `page.title`, `page.status_{status_code}`,
            and `page.back_to_home`. Defaults to None.
        status_codes (tuple[int, ...], optional): A tuple of HTTP status codes to
            intercept. Defaults to (404, 403, 500, 503).
    """

    def __init__(
        self,
        app: ASGIApp,
        favicon_url: str | None = None,
        template_path: Path | str = "error.html",
        translator: Any | None = None,
        status_codes: tuple[int, ...] = (404, 403, 500, 503),
    ) -> None:
        self.app = app
        self.template_path = template_path
        self.favicon_url = favicon_url
        self.translator = translator
        self.status_codes = status_codes

        self._html_cache = None

        raw_html = self._get_raw_html()
        required_placeholders = [
            "{{ status_code }}",
            "{{ title }}",
            "{{ error_message }}",
            "{{ favicon_url }}",
            "{{ action_button }}",
        ]
        missing = [p for p in required_placeholders if p not in raw_html]
        if missing:
            raise RuntimeError(
                f"Error page template at {self.template_path} is missing required placeholders: {', '.join(missing)}"
            )

    def _get_raw_html(self) -> str:
        if self._html_cache is not None:
            return self._html_cache

        path = Path(self.template_path)
        if not path.is_absolute():
            path = Path(__file__).parent / path

        try:
            self._html_cache = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning(f"Error page template not found at {path}, using fallback.")
            self._html_cache = (
                "<!DOCTYPE html><html><head><title>{{ title }}</title>"
                '<link rel="icon" href="{{ favicon_url }}" type="image/x-icon" />'
                "</head><body><h1>{{ status_code }}</h1>"
                "<p>{{ error_message }}</p>{{ action_button }}</body></html>"
            )

        return self._html_cache

    def _render_html(self, status_code: int, is_same_origin: bool = False) -> bytes:
        html = self._get_raw_html()

        html = html.replace("{{ status_code }}", str(status_code))

        if self.favicon_url:
            html = html.replace("{{ favicon_url }}", self.favicon_url)
        else:
            html = html.replace("{{ favicon_url }}", "/favicon.ico")

        title = f"{status_code} Error"
        error_message = "An unexpected error occurred."
        back_to_home = "Back to Home"
        go_back = "Go Back"

        if status_code == 403:
            error_message = "You do not have permission to view this page."
        elif status_code == 404:
            error_message = "We couldn't find the page you were looking for."
        elif status_code == 503:
            error_message = "Service unavailable. We are currently undergoing maintenance."

        if self.translator:
            try:
                translated_title = self.translator("seo.error.title", status_code=status_code)
                if translated_title != "seo.error.title":
                    title = translated_title
                else:
                    fallback_title = self.translator("page.title")
                    if fallback_title != "page.title":
                        title = f"{status_code} - {fallback_title}"

                translated_msg = self.translator(f"page.status_{status_code}")
                if translated_msg != f"page.status_{status_code}":
                    error_message = translated_msg

                translated_back = self.translator("page.back_to_home")
                if translated_back != "page.back_to_home":
                    back_to_home = translated_back

                translated_go = self.translator("page.go_back")
                if translated_go != "page.go_back":
                    go_back = translated_go
            except Exception:
                pass

        if is_same_origin:
            action_button = f'<button type="button" class="btn" onclick="window.history.back();" style="cursor: pointer; font-family: inherit;">{go_back}</button>'
        else:
            action_button = f"""<a href="/" class="btn" id="fallback-btn">{back_to_home}</a>
            <script>
                if (window.history.length > 1) {{
                    var btn = document.getElementById('fallback-btn');
                    if (btn) {{
                        btn.href = '#';
                        btn.innerText = '{go_back}';
                        btn.onclick = function(e) {{
                            e.preventDefault();
                            window.history.back();
                        }};
                    }}
                }}
            </script>"""

        html = html.replace("{{ title }}", title)
        html = html.replace("{{ error_message }}", error_message)
        html = html.replace("{{ action_button }}", action_button)

        return html.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        accept = request.headers.get("accept", "")

        if "text/html" not in accept:
            await self.app(scope, receive, send)
            return

        started = False
        response_started = False
        status_code = 200
        headers_to_send = None

        referer = request.headers.get("referer") or ""
        origin = str(request.base_url)
        is_same_origin = referer.startswith(origin)

        async def send_wrapper(message: Message) -> None:
            nonlocal started, response_started, status_code, headers_to_send

            if message["type"] == "http.response.start":
                status_code = message["status"]
                if status_code in self.status_codes:
                    started = True
                    headers_to_send = message.get("headers", [])
                    return
                response_started = True
                await send(message)
                return

            if started and message["type"] == "http.response.body":
                if not message.get("more_body", False) and not response_started:
                    response_started = True
                    html_content = self._render_html(status_code, is_same_origin)
                    resp = HTMLResponse(content=html_content, status_code=status_code)
                    await resp(scope, receive, send)
                return

            if not started:
                await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            if not response_started:
                response_started = True
                logger.error(f"Unhandled exception caught by ErrorPageMiddleware: {e}")
                html_content = self._render_html(500, is_same_origin)
                response = HTMLResponse(content=html_content, status_code=500)
                await response(scope, receive, send)
            else:
                raise e
