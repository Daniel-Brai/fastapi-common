from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request, status
from sqlmodel import select

from lib.auth.config import get_hasher, get_user_model
from lib.auth.enums import SessionStatus, TokenStatus
from lib.auth.exceptions import TokenExpired, TokenInvalid, TokenRevoked
from lib.auth.helpers import auth_error_to_http, consume_token, db_session, generate_token, user_by_email
from lib.auth.jobs import SendAuthEmailJob
from lib.auth.models import RefreshToken, Session
from lib.auth.options import AuthOptions
from lib.auth.schemas import AuthForgotPasswordRequest, AuthResetPasswordRequest
from lib.auth.throttler import get_throttler_for_router
from lib.ext.fastapi import IBaseResponse, ORJSONResponse, build_orjson_response
from lib.logger import get_logger

logger = get_logger("lib.auth.flows.passwords")


def get_passwords_router(
    options: AuthOptions,
) -> APIRouter:
    """
    Create a router with the password reset routes.

    Returns:
        APIRouter: The passwords router to be included in the main auth router.
    """

    passwords_router = APIRouter()

    rate_limit_dependencies = get_throttler_for_router(options, "accounts")

    @passwords_router.post(
        "/forgot-password",
        status_code=status.HTTP_200_OK,
        operation_id="forgot_password",
        response_model=IBaseResponse,
        dependencies=rate_limit_dependencies.get("forgot_password", []),
    )
    async def forgot_password(
        request: Request,
        body: Annotated[
            AuthForgotPasswordRequest,
            Body(
                ...,
                description="Email address of the account to reset the password for.",
            ),
        ],
    ) -> ORJSONResponse:
        """
        Request a password reset email.

        Always returns 200 regardless of whether the email exists.

        If the email is unknown, the response is identical to a successful request.
        """
        user = await user_by_email(body.email)

        if user and user.is_active:
            try:
                token = await generate_token(
                    kind="password_reset",
                    user_id=user.id,
                    requested_from=request.client.host if request.client else None,
                )

                SendAuthEmailJob.perform_later("send_password_reset", to=user.email, token=token)
            except Exception:
                logger.exception("Failed to send password reset to %s", body.email)

        return build_orjson_response(
            message="If that email is registered, a reset link has been sent.",
            base=True,
        )

    @passwords_router.post(
        "/reset-password",
        status_code=status.HTTP_200_OK,
        operation_id="reset_password",
        response_model=IBaseResponse,
        dependencies=rate_limit_dependencies.get("reset_password", []),
    )
    async def reset_password(
        body: Annotated[
            AuthResetPasswordRequest,
            Body(..., description="Password reset token and new password."),
        ],
    ) -> ORJSONResponse:
        """
        Consume a password reset token and set a new password.

        Invalidates all active sessions / refresh tokens for the user.
        """

        try:
            rec = await consume_token(kind="password_reset", token=body.token)
        except (TokenInvalid, TokenRevoked, TokenExpired) as exc:
            raise auth_error_to_http(exc) from exc

        async with db_session() as s:
            user = s.get(get_user_model(), rec.user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

            user.hashed_password = get_hasher().hash(body.password, user.password_salt)
            user.updated_at = datetime.now()
            s.add(user)

            tokens = s.exec(
                select(RefreshToken)
                .where(RefreshToken.user_id == user.id)
                .where(RefreshToken.status == TokenStatus.ACTIVE)
            ).all()

            for t in tokens:
                t.status = TokenStatus.REVOKED
                t.revoked_at = datetime.now()
                s.add(t)

            sessions = s.exec(
                select(Session).where(Session.user_id == user.id).where(Session.status == SessionStatus.ACTIVE)
            ).all()

            for sess in sessions:
                sess.status = SessionStatus.REVOKED
                sess.revoked_at = datetime.now()
                s.add(sess)

            s.commit()
            s.refresh(user)

        try:
            SendAuthEmailJob.perform_later("send_password_changed_notice", to=user.email)
        except Exception:
            logger.warning("Could not send password-changed notice to %s", user.email)

        return build_orjson_response(message="Password updated. Please log in with your new password.", base=True)

    return passwords_router
