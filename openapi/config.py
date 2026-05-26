from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from lib.openapi.middleware import OpenAPISecurityMiddleware


def configure_openapi(
    app: FastAPI,
    username: str,
    password: str,
    *,
    docs_url: str = "/docs",
    json_schema_url: str = "/openapi.json",
    use_default_security: bool = True,
) -> None:
    """
    Configure protected OpenAPI docs and schema routes for a FastAPI app.

    This helper mounts two endpoints:
    - ``docs_url``: Swagger UI HTML page.
    - ``json_schema_url`` (prefixed by ``docs_url``): OpenAPI JSON schema.

    By default, both routes are protected with :class:`OpenAPISecurityMiddleware`
    using HTTP Basic credentials.

    Parameters
    ----------
    app
        FastAPI application instance to configure.
    username
        Username used by ``OpenAPISecurityMiddleware`` when
        ``use_default_security=True``.
    password
        Password used by ``OpenAPISecurityMiddleware`` when
        ``use_default_security=True``.
    docs_url
        URL path where Swagger UI is exposed. Defaults to ``"/docs"``.
        Trailing slashes are removed.
    json_schema_url
        Path suffix for the OpenAPI JSON schema, appended to ``docs_url``.
        Defaults to ``"/openapi.json"``.
        Example: ``docs_url="/docs"`` and ``json_schema_url="/openapi.json"``
        yields ``/docs/openapi.json``.
    use_default_security
        Whether to install ``OpenAPISecurityMiddleware`` for protecting docs
        and schema endpoints. Defaults to ``True``.

    Returns
    -------
    None
    """

    docs_url = docs_url.rstrip("/")
    json_schema_url = f"{docs_url}{json_schema_url}"

    if use_default_security:
        app.add_middleware(
            OpenAPISecurityMiddleware,
            username=username,
            password=password,
            docs_url=docs_url,
            json_schema_url=json_schema_url,
        )

    @app.get(
        docs_url,
        include_in_schema=False,
        response_class=HTMLResponse,
    )
    async def get_swagger_documentation() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=json_schema_url,
            title=f"{app.title} API Documentation",
            swagger_ui_parameters={"persistAuthorization": True},
        )

    @app.get(
        json_schema_url,
        include_in_schema=False,
    )
    async def openapi() -> dict[str, Any]:
        openapi_schema = get_openapi(
            title=app.title,
            description=f"API documentation for {app.title.title()}.",
            version=app.version,
            routes=app.routes,
        )

        return openapi_schema
