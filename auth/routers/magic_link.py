from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Path, Request, status

from lib.auth.config import get_backend, get_user_model
from lib.auth.exceptions import AuthError, TokenExpired, TokenInvalid, TokenRevoked
from lib.auth.helpers import (
    auth_error_to_http,
    consume_token,
    db_commit,
    db_get,
    db_refresh,
    db_session,
    generate_token,
    user_by_email,
)
from lib.auth.jobs import SendAuthEmailJob
from lib.auth.options import AuthOptions
from lib.auth.schemas import AuthMagicLinkRequest, AuthSessionResponse, AuthUserResponse
from lib.auth.throttler import get_throttler_for_router
from lib.ext.fastapi import IBaseResponse, IResponse, ORJSONResponse, build_orjson_response
from lib.logger import get_logger

logger = get_logger("lib.auth.flows.magic_links")


def get_magic_link_router(options: AuthOptions) -> APIRouter | None:

    if options.magic_links_enabled:

        magic_link_router = APIRouter()

        rate_limit_dependencies = get_throttler_for_router(options, "magic_link")

        @magic_link_router.post(
            "/magic-link",
            status_code=status.HTTP_200_OK,
            operation_id="request_magic_link",
            response_model=IBaseResponse,
            dependencies=rate_limit_dependencies.get("request_magic_link", []),
        )
        async def request_magic_link(
            request: Request,
            body: Annotated[
                AuthMagicLinkRequest,
                Body(..., description="Email address to send the magic link to"),
            ],
        ) -> ORJSONResponse:
            """
            Send a one-click login link to the given email.

            Always returns 200 OK to prevent email enumeration, but only sends a link if the email is registered and active.
            """

            user = await user_by_email(body.email)

            if user and user.is_active:
                try:
                    token = await generate_token(
                        kind="magic_link",
                        user_id=user.id,
                        requested_from=request.client.host if request.client else None,
                        ttl=timedelta(minutes=15),
                    )

                    SendAuthEmailJob.perform_later("send_magic_link", to=user.email, token=token)
                except Exception as exc:
                    logger.exception("Failed to send magic link email to user_id=%s", user.id)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to send magic link email",
                    ) from exc

            return build_orjson_response(
                message="If that email is registered, a sign-in link has been sent.", base=True
            )

        @magic_link_router.get(
            "/magic-link/{token}",
            status_code=status.HTTP_200_OK,
            operation_id="consume_magic_link",
            dependencies=rate_limit_dependencies.get("consume_magic_link", []),
            response_model=IResponse[AuthSessionResponse, None],
        )
        async def consume_magic_link(
            request: Request,
            token: Annotated[str, Path(..., description="Magic link token")],
        ) -> ORJSONResponse:
            """
            Consume a magic link token and issue credentials (session or JWT pair).

            The link is single-use and expires after 15 minutes.

            Returns:
                200 OK with auth credentials if the token is valid and the user is active.
                400 Bad Request if the token is invalid, expired, or revoked.
                404 Not Found if the user associated with the token does not exist or is inactive.

            Format of returned credentials depends on the configured auth backend (e.g. session cookie or JWT access/refresh tokens).
            """

            try:
                rec = await consume_token(kind="magic_link", token=token)
            except (TokenInvalid, TokenRevoked, TokenExpired) as exc:
                raise auth_error_to_http(exc) from exc

            async with db_session() as s:
                user = await db_get(s, get_user_model(), rec.user_id)
                if not user or not user.is_active:
                    raise HTTPException(status_code=404, detail="User not found")

                if not user.email_verified:
                    user.email_verified = True
                    user.updated_at = datetime.now()
                    s.add(user)
                    await db_commit(s)

                await db_refresh(s, user)

            try:
                backend = get_backend()
                result = await backend.login(user, request, None, attach=False)
            except AuthError as exc:
                logger.exception("Failed to log in user_id=%s via magic link: %s", rec.user_id, exc)
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
                message="Magic link verified successfully",
                data=response_data,
            )

            if hasattr(result, "access_token") and hasattr(result, "refresh_token"):
                backend.attach(result, response)
            elif hasattr(result, "session_id"):
                backend.attach(result.session_id, response)

            return response

        return magic_link_router
