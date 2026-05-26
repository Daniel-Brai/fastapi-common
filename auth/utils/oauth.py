from dataclasses import asdict
from typing import Any

from fastapi import HTTPException, Request, status

from lib.auth.config import get_backend, resolve_provider
from lib.auth.exceptions import AuthError, OAuthError
from lib.auth.helpers import auth_error_to_http, find_or_create_oauth_user
from lib.auth.schemas import AuthUserResponse
from lib.ext.fastapi import build_orjson_response


async def handle_oauth_callback(provider: str, request: Request):
    try:
        p = resolve_provider(provider)
    except AuthError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider {provider!r} not registered")

    try:
        info = p.handle_callback(request)
    except OAuthError as exc:
        raise auth_error_to_http(exc)

    user = await find_or_create_oauth_user(
        provider=info.provider,
        sub=info.sub,
        email=info.email,
        email_verified=info.email_verified,
        name=info.name,
        access_token=info.access_token,
        refresh_token=info.refresh_token,
        id_token=info.id_token,
        token_expires_at=info.token_expires_at,
        extra=info.extra,
    )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    try:
        backend = get_backend()
        result = await backend.login(user, request, None, attach=False)
    except AuthError as exc:
        raise auth_error_to_http(exc) from exc

    response_data: dict[str, Any] = {
        "user": AuthUserResponse.from_user(user).model_dump(),
    }

    def attach_tokens(result: Any, response_data: dict[str, Any]) -> dict[str, Any]:
        if hasattr(result, "access_token") and hasattr(result, "refresh_token"):
            auth_data = asdict(result)
            response_data["token"] = auth_data
            return response_data

        response_data["token"] = None
        return response_data

    response_data: dict[str, Any] = attach_tokens(result, response_data)

    response = build_orjson_response(
        message="OAuth login successful",
        data=response_data,
    )

    if hasattr(result, "access_token") and hasattr(result, "refresh_token"):
        backend.attach(result, response)
    elif hasattr(result, "session_id"):
        backend.attach(result.session_id, response)

    if hasattr(p, "clear_state_cookie"):
        p.clear_state_cookie(response)  # type: ignore[attr-defined]

    return response
