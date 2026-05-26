from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import RedirectResponse

from lib.auth.config import resolve_provider
from lib.auth.exceptions import AuthConfigError
from lib.auth.schemas import AuthSessionTokenResponse
from lib.auth.utils import handle_oauth_callback
from lib.ext.fastapi import IResponse, ORJSONResponse

oauth_router = APIRouter()


@oauth_router.get("/oauth/{provider}/redirect")
def oauth_redirect(
    request: Request,
    provider: Annotated[str, Path(description="OAuth provider name, e.g. 'google' or 'github'")],
) -> RedirectResponse:
    """
    Start the OAuth flow for `provider`.

    Redirects the browser to the provider's authorization page.
    """

    try:
        p = resolve_provider(provider)
    except AuthConfigError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider {provider!r} not registered",
        )

    url, signed_state = p.get_redirect_url(request)

    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    if hasattr(p, "set_state_cookie"):
        p.set_state_cookie(response, signed_state)  # type: ignore[attr-defined]
    else:
        response.set_cookie(
            f"{provider}_state",
            signed_state,
            max_age=600,
            httponly=True,
            samesite="lax",
        )

    return response


@oauth_router.get(
    "/oauth/{provider}/callback",
    operation_id="oauth_callback_get",
    status_code=status.HTTP_200_OK,
    response_model=IResponse[AuthSessionTokenResponse, None],
)
async def oauth_callback_get(
    request: Request,
    provider: Annotated[str, Path(description="OAuth provider name, e.g. 'google' or 'github'")],
) -> ORJSONResponse:
    """
    OAuth callback GET variant (Google, GitHub, etc.).
    """
    return await handle_oauth_callback(provider, request)


@oauth_router.post(
    "/oauth/{provider}/callback",
    operation_id="oauth_callback_post",
    status_code=status.HTTP_200_OK,
    response_model=IResponse[AuthSessionTokenResponse, None],
)
async def oauth_callback_post(
    request: Request,
    provider: Annotated[str, Path(description="OAuth provider name, e.g. 'google' or 'github'")],
) -> ORJSONResponse:
    """
    OAuth callback POST variant (Apple Sign In uses form_post).
    """
    try:
        form_data = await request.form()
        request.state.form_data = {key: str(value) for key, value in form_data.items()}

        from starlette.datastructures import QueryParams

        merged: dict[str, str] = dict(request.query_params)

        merged.update(request.state.form_data)
        request._query_params = QueryParams(merged)

    except Exception:
        pass

    return await handle_oauth_callback(provider, request)
