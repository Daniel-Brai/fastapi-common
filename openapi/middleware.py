import base64

from fastapi import Request, status
from starlette.types import ASGIApp

from lib.logger import get_logger
from lib.openapi.exceptions import OpenAPIAuthError

logger = get_logger("lib.openapi.middleware")


class OpenAPISecurityMiddleware:
    """
    Middleware to protect OpenAPI docs and schema endpoints with basic auth.

    Parameters
    ----------
    app
        The ASGI application (passed automatically by add_middleware).
    username
        The required username for accessing the docs and schema.
    password
        The required password for accessing the docs and schema.
    docs_url
        The URL path for the OpenAPI docs (e.g. "/docs").
    json_schema_url
        The URL path for the OpenAPI JSON schema (e.g. "/openapi.json").

    Usage:

        app.add_middleware(
            OpenAPISecurityMiddleware,
            username="admin",
            password="secret",
            docs_url="/docs",
            json_schema_url="/openapi.json",
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        username: str,
        password: str,
        docs_url: str,
        json_schema_url: str,
    ) -> None:
        self.app = app
        self.docs_url = docs_url
        self.json_schema_url = json_schema_url
        self.username = username
        self.password = password

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http":
            request = Request(scope, receive=receive)
            if request.url.path in [
                self.docs_url,
                self.json_schema_url,
            ]:
                auth_header = request.headers.get("authorization")
                if not auth_header:
                    raise OpenAPIAuthError(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        message="Missing authorization header",
                        headers={"WWW-Authenticate": 'Basic realm="OpenAPI Documentation"'},
                    )

                try:
                    auth_type, auth_value = auth_header.split()
                    if auth_type.lower() != "basic":
                        raise OpenAPIAuthError(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            message="Invalid authentication format",
                            headers={"WWW-Authenticate": 'Basic realm="OpenAPI Documentation"'},
                        )

                    decoded = base64.b64decode(auth_value).decode()
                    username, password = decoded.split(":")

                    if username != self.username or password != self.password:
                        raise OpenAPIAuthError(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            message="Invalid credentials",
                            headers={"WWW-Authenticate": 'Basic realm="OpenAPI Documentation"'},
                        )

                except Exception as exc:
                    raise OpenAPIAuthError(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        message="Invalid authorization header",
                        headers={"WWW-Authenticate": 'Basic realm="OpenAPI Documentation"'},
                    ) from exc

        await self.app(scope, receive, send)
