from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, Request, status

from lib.auth.config import get_user_model
from lib.auth.exceptions import TokenExpired, TokenInvalid, TokenRevoked
from lib.auth.helpers import auth_error_to_http, consume_token, db_session, generate_token, user_by_email
from lib.auth.jobs import SendAuthEmailJob
from lib.auth.options import AuthOptions
from lib.auth.schemas import AuthSendVerificationEmailRequest
from lib.auth.throttler import get_throttler_for_router
from lib.ext.fastapi import IBaseResponse, ORJSONResponse, build_orjson_response, get_client_ip
from lib.logger import get_logger

logger = get_logger("lib.auth.flows.email_verification")


def get_email_verification_router(
    options: AuthOptions,
) -> APIRouter:
    """
    Create a router with the email verification routes.

    Returns:
        APIRouter: The email verification router to be included in the main auth router.
    """

    email_verification_router = APIRouter()

    rate_limit_dependencies = get_throttler_for_router(options, "email_verification")

    @email_verification_router.post(
        "/verify-email/send",
        status_code=status.HTTP_200_OK,
        operation_id="send_verification_email",
        dependencies=rate_limit_dependencies.get("send_verification_email", []),
        response_model=IBaseResponse,
    )
    async def send_verification_email(
        request: Request,
        body: Annotated[
            AuthSendVerificationEmailRequest,
            Body(..., description="Email address to send the verification link to"),
        ],
    ) -> ORJSONResponse:
        """
        (Re)send the email verification link to the requested email.
        """

        user = await user_by_email(body.email)

        if not user:
            return build_orjson_response(
                message="If the email is registered, we have sent a verification link.",
                base=True,
            )

        if user.email_verified:
            return build_orjson_response(message="Email is already verified.", base=True)

        try:
            token = await generate_token(
                kind="email_verification",
                user_id=user.id,
                requested_from=get_client_ip(request),
            )
            SendAuthEmailJob.perform_later("send_verification_email", to=user.email, token=token)
        except Exception:
            logger.exception("Failed to send verification email to user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to send verification email",
            )

        return build_orjson_response(
            message="If the email is registered, we have sent a verification link.",
            base=True,
        )

    @email_verification_router.get(
        "/verify-email/{token}",
        operation_id="verify_email",
        status_code=status.HTTP_200_OK,
        dependencies=rate_limit_dependencies.get("verify_email", []),
        response_model=IBaseResponse,
    )
    async def verify_email(
        token: Annotated[str, Path(description="Email verification token")],
    ) -> ORJSONResponse:
        """
        Consume an email verification token.

        Marks the user's email as verified.
        """

        try:
            rec = await consume_token(kind="email_verification", token=token)
        except (TokenInvalid, TokenRevoked, TokenExpired) as exc:
            raise auth_error_to_http(exc) from exc

        async with db_session() as s:
            user = s.get(get_user_model(), rec.user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

            if user.email_verified:
                return build_orjson_response(message="Email already verified.", base=True)

            user.email_verified = True
            user.updated_at = datetime.now()
            s.add(user)
            s.commit()

        return build_orjson_response(message="Email address verified successfully.", base=True)

    return email_verification_router
