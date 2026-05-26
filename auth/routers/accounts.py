from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status
from sqlmodel import select

from lib.auth.backends import JWTBackend, SessionBackend
from lib.auth.config import get_authorization_defaults, get_backend, get_hasher, get_user_model
from lib.auth.enums import SessionStatus, TokenStatus
from lib.auth.exceptions import AccountScheduledForDeletion, AuthError, TokenExpired, TokenInvalid, TokenRevoked
from lib.auth.helpers import (
    auth_error_to_http,
    consume_token,
    db_commit,
    db_exec,
    db_refresh,
    db_session,
    generate_token,
    user_by_email,
)
from lib.auth.jobs import SendAuthEmailJob
from lib.auth.models import RefreshToken, Session
from lib.auth.options import AuthOptions
from lib.auth.schemas import (
    AuthChangeEmailRequest,
    AuthChangePasswordRequest,
    AuthLoginRequest,
    AuthRecoverAccountRequest,
    AuthRegisterRequest,
    AuthSessionResponse,
    AuthSessionTokenResponse,
    AuthUserResponse,
)
from lib.auth.throttler import get_throttler_for_router
from lib.auth.user import AuthUserMixin
from lib.ext.fastapi import IBaseResponse, IResponse, ORJSONResponse, build_orjson_response, get_client_ip
from lib.logger import get_logger

logger = get_logger("lib.auth.flows.accounts")


def get_accounts_router(auth_dep: Callable, options: AuthOptions) -> APIRouter:
    """
    Create a router with the core account management routes: register, login, logout, refresh, change email/password, delete account.

    Returns:
        APIRouter: The accounts router to be included in the main auth router.
    """

    accounts_router = APIRouter()

    rate_limit_dependencies = get_throttler_for_router(options, "accounts")

    if options.registration_enabled is True:

        @accounts_router.post(
            "/register",
            status_code=status.HTTP_200_OK,
            operation_id="register",
            response_model=IResponse[AuthSessionResponse, None],
            dependencies=rate_limit_dependencies.get("register", []),
        )
        async def register(
            request: Request,
            body: Annotated[
                AuthRegisterRequest,
                Body(..., description="Registration details for a new user"),
            ],
        ) -> ORJSONResponse:
            """
            Register a new user with email and password.

            Automatically logs them in — sets session cookie or returns TokenPair.
            """

            async with db_session() as s:
                UserModel = get_user_model()
                _r = await db_exec(s, select(UserModel).where(UserModel.email == body.email))

                existing = _r.first()
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email already registered",
                    )

                user_attrs: dict[str, Any] = {
                    "email": body.email,
                }
                user_attrs.update(get_authorization_defaults(UserModel))

                model_fields = getattr(UserModel, "model_fields", {})
                if body.name is not None and "name" in model_fields:
                    user_attrs["name"] = body.name

                if "roles" not in user_attrs and "roles" in model_fields:
                    user_attrs["roles"] = []

                user = UserModel(**user_attrs)  # type: ignore[arg-type]
                user.hashed_password = get_hasher().hash(body.password, user.password_salt)
                s.add(user)
                await db_commit(s)
                await db_refresh(s, user)

            try:
                backend = get_backend()

                if backend.auto_login():
                    result = await backend.login(user, request, None, attach=False)
                else:
                    token = await generate_token(
                        kind="email_verification",
                        user_id=user.id,
                        requested_from=get_client_ip(request),
                    )
                    SendAuthEmailJob.perform_later("send_verification_email", to=user.email, token=token)
                    result = None
            except AuthError as exc:
                logger.exception("Failed to register user user_id=%s: %s", user.id, exc)
                raise auth_error_to_http(exc) from exc

            response_data: dict[str, Any] = {
                "user": AuthUserResponse.from_user(user).model_dump(),
            }

            if result is None:
                return build_orjson_response(
                    message="User registered successfully. Please check your email to verify your account.",
                    data=response_data,
                )

            def attach_tokens(result: Any, response_data: dict[str, Any]) -> dict[str, Any]:
                if hasattr(result, "access_token") and hasattr(result, "refresh_token"):
                    auth_data = asdict(result)
                    response_data["token"] = auth_data
                    return response_data

                response_data["token"] = None
                return response_data

            response_data: dict[str, Any] = attach_tokens(result, response_data)

            response = build_orjson_response(
                message="User registered successfully",
                data=response_data,
            )

            if hasattr(result, "access_token") and hasattr(result, "refresh_token"):
                backend.attach(result, response)
            elif hasattr(result, "session_id"):
                backend.attach(result.session_id, response)

            return response

    @accounts_router.post(
        "/login",
        status_code=status.HTTP_200_OK,
        operation_id="login",
        response_model=IResponse[AuthSessionResponse, None],
        dependencies=rate_limit_dependencies.get("login", []),
    )
    async def login(
        request: Request,
        body: Annotated[
            AuthLoginRequest,
            Body(..., description="Login credentials with email and password"),
        ],
    ) -> ORJSONResponse:
        """
        Authenticate with email and password.
        """

        UserModel = get_user_model()
        async with db_session() as s:
            _r = await db_exec(s, select(UserModel).where(UserModel.email == body.email))
            user = _r.first()

        if not user or not user.hashed_password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if user and not get_hasher().verify(body.password, user.password_salt, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if user and not user.email_verified:
            try:
                token = await generate_token(
                    kind="email_verification",
                    user_id=user.id,
                    requested_from=get_client_ip(request),
                )
                SendAuthEmailJob.perform_later("send_verification_email", to=user.email, token=token)
            except Exception:
                logger.exception(
                    "Failed to send email verification during login for user_id=%s",
                    user.id,
                )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email address is not verified. We've sent you an email with a verification link. Please check your inbox.",
            )

        if user and not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")

        if options.deletion_style == "soft" and getattr(user, "deleted_at", None):
            from datetime import datetime, timezone

            deletion_time = user.deleted_at
            if deletion_time.tzinfo is None:
                deletion_time = deletion_time.replace(tzinfo=timezone.utc)

            final_deletion = deletion_time + timedelta(days=options.deletion_grace_period_days)
            days_left = (final_deletion - datetime.now(timezone.utc)).days
            days_left = max(0, days_left)

            raise AccountScheduledForDeletion(
                detail=f"Your account has been scheduled for deletion in {days_left} days. You can recover your account if you want to."
            )

        try:
            backend = get_backend()
            result = await backend.login(user, request, None, attach=False)
        except AuthError as exc:
            logger.exception("Failed to login user user_id=%s: %s", user.id, exc)
            raise auth_error_to_http(exc) from exc
        except Exception as exc:
            logger.exception("Unexpected error during login for user_id=%s: %s", user.id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during login. Please try again later.",
            ) from exc

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
            message="User logged in successfully",
            data=response_data,
        )

        if hasattr(result, "access_token") and hasattr(result, "refresh_token"):
            backend.attach(result, response)
        elif hasattr(result, "session_id"):
            backend.attach(result.session_id, response)

        return response

    @accounts_router.post(
        "/logout",
        status_code=status.HTTP_200_OK,
        operation_id="logout",
        response_model=IBaseResponse,
        dependencies=[Depends(auth_dep), *rate_limit_dependencies.get("logout", [])],
    )
    async def logout(request: Request) -> ORJSONResponse:
        """
        Revoke the current session or refresh token family.
        """

        backend = get_backend()

        response = build_orjson_response(message="Logged out successfully.", base=True)

        await backend.logout(request, response)

        return response

    @accounts_router.post(
        "/refresh",
        status_code=status.HTTP_200_OK,
        operation_id="refresh",
        response_model=IResponse[AuthSessionTokenResponse, None],
        dependencies=[Depends(auth_dep), *rate_limit_dependencies.get("refresh", [])],
    )
    async def refresh(request: Request) -> ORJSONResponse:
        """
        JWT only: rotate the refresh token and issue a new TokenPair.
        The refresh token is read from the httpOnly cookie set at login.
        """
        try:
            backend = get_backend()

            if not isinstance(backend, JWTBackend):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Token refresh is only supported for JWT authentication",
                )

            result = await backend.refresh(request, response=None, attach=False)
        except AuthError as exc:
            raise auth_error_to_http(exc) from exc

        return build_orjson_response(
            message="Token refreshed successfully",
            data={"token": asdict(result)},
        )

    @accounts_router.get(
        "/me",
        status_code=status.HTTP_200_OK,
        operation_id="me",
        response_model=IResponse[AuthUserResponse, None],
        dependencies=rate_limit_dependencies.get("me", []),
    )
    async def me(
        user: Annotated[AuthUserMixin, Depends(auth_dep)],
    ) -> ORJSONResponse:
        """
        Return the currently authenticated user.
        """

        return build_orjson_response(
            message="Current user retrieved successfully",
            data={"user": AuthUserResponse.from_user(user).model_dump()},
        )

    @accounts_router.post(
        "/change-password",
        status_code=status.HTTP_200_OK,
        operation_id="change_password",
        response_model=IBaseResponse,
        dependencies=rate_limit_dependencies.get("change_password", []),
    )
    async def change_password(
        request: Request,
        user: Annotated[AuthUserMixin, Depends(auth_dep)],
        body: Annotated[
            AuthChangePasswordRequest,
            Body(
                ...,
                description="Request body for changing the password of the authenticated user.",
            ),
        ],
    ) -> ORJSONResponse:
        """
        Change the password for the authenticated user.

        Requires the current password (prevents session-hijack escalation).

        Invalidates all other sessions / refresh tokens after the change.
        """

        if not user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This account uses social loggerin and has no password to change.",
            )

        if not get_hasher().verify(body.current_password, user.password_salt, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )

        backend = get_backend()

        async with db_session() as s:
            u = s.get(get_user_model(), user.id)
            u.hashed_password = get_hasher().hash(body.new_password, u.password_salt)
            u.updated_at = datetime.now()
            s.add(u)

            if isinstance(backend, JWTBackend):
                tokens = s.exec(
                    select(RefreshToken)
                    .where(RefreshToken.user_id == user.id)
                    .where(RefreshToken.status == TokenStatus.ACTIVE)
                ).all()

                for t in tokens:
                    t.status = TokenStatus.REVOKED
                    t.revoked_at = datetime.now()
                    s.add(t)

            elif isinstance(backend, SessionBackend):
                current_session_id = request.cookies.get(backend.cookie_name)
                if current_session_id:
                    sessions = s.exec(
                        select(Session)
                        .where(Session.user_id == user.id)
                        .where(Session.status == SessionStatus.ACTIVE)
                        .where(Session.session_id != current_session_id)
                    ).all()

                    for sess in sessions:
                        sess.status = SessionStatus.REVOKED
                        sess.revoked_at = datetime.now()
                        s.add(sess)

            s.commit()

        try:
            SendAuthEmailJob.perform_later("send_password_changed_notice", to=user.email)
        except Exception:
            logger.warning("Could not send password-changed notice to %s", user.email)

        return build_orjson_response(message="Password changed successfully.")

    @accounts_router.post(
        "/change-email",
        status_code=status.HTTP_200_OK,
        operation_id="change_email",
        response_model=IBaseResponse,
        dependencies=rate_limit_dependencies.get("change_email", []),
    )
    async def change_email(
        request: Request,
        user: Annotated[AuthUserMixin, Depends(auth_dep)],
        body: Annotated[
            AuthChangeEmailRequest,
            Body(
                ...,
                description="Request body for changing the email address of the authenticated user.",
            ),
        ],
    ) -> ORJSONResponse:
        """
        Initiate an email address change.

        Sends a verification link to the *new* address.

        The change is not applied until the link is clicked (verify-email-change).

        For password-based accounts, requires the current password.
        """

        if user.hashed_password:
            if not body.current_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is required to change your email address.",
                )

            if not get_hasher().verify(body.current_password, user.password_salt, user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Current password is incorrect",
                )

        existing = await user_by_email(body.new_email)
        if existing and existing.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address is already in use",
            )

        try:
            token = await generate_token(
                kind="email_change",
                user_id=user.id,
                payload=str(body.new_email),  # the new address stored in OTT
                requested_from=request.client.host if request.client else None,
            )

            SendAuthEmailJob.perform_later(
                "send_email_change_verification",
                to=str(body.new_email),
                token=token,
                new_email=str(body.new_email),
            )
        except Exception:
            logger.exception("Failed to send email change verification for user_id=%s", user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to send verification email",
            )

        return build_orjson_response(message="Verification email sent to your new address.", base=True)

    @accounts_router.get(
        "/verify-email-change/{token}",
        status_code=status.HTTP_200_OK,
        operation_id="verify_email_change",
        response_model=IBaseResponse,
    )
    async def verify_email_change(
        token: Annotated[
            str,
            Path(
                ...,
                description="One-time token sent to the new email address for verification.",
            ),
        ],
    ) -> ORJSONResponse:
        """
        Consume an email change token and apply the new address.

        Sends a security notice to the old address.
        """

        try:
            rec = await consume_token(kind="email_change", token=token)
        except (TokenInvalid, TokenRevoked, TokenExpired) as exc:
            raise auth_error_to_http(exc) from exc

        new_email = rec.payload
        if not new_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token is malformed")

        async with db_session() as s:
            user = s.get(get_user_model(), rec.user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

            old_email = user.email

            clash = s.exec(
                select(get_user_model())
                .where(get_user_model().email == new_email)
                .where(get_user_model().id != user.id)
            ).first()

            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email address is already in use",
                )

            user.email = new_email
            user.email_verified = True
            user.updated_at = datetime.now()
            s.add(user)
            s.commit()

        try:
            SendAuthEmailJob.perform_later("send_email_changed_notice", to=old_email)
        except Exception:
            logger.warning("Could not send email-changed notice to old address %s", old_email)

        return build_orjson_response(message="Email address updated successfully.", base=True)

    if options.deletion_style == "soft":

        @accounts_router.delete(
            "/me",
            status_code=status.HTTP_200_OK,
            operation_id="delete_account_soft",
            response_model=IBaseResponse,
        )
        async def delete_account(
            request: Request,
            user: Annotated[AuthUserMixin, Depends(auth_dep)],
        ) -> ORJSONResponse:
            """
            Soft-delete the current user's account.

            Sets is_active=False and revokes all sessions/tokens.

            Does not physically delete the row so FK integrity is maintained.

            Provide a hard-delete variant if your compliance requirements demand it.
            """

            async with db_session() as s:
                u = s.get(get_user_model(), user.id)
                u.is_active = False
                u.updated_at = datetime.now()
                s.add(u)

                backend = get_backend()
                if isinstance(backend, JWTBackend):
                    for t in s.exec(
                        select(RefreshToken)
                        .where(RefreshToken.user_id == user.id)
                        .where(RefreshToken.status == TokenStatus.ACTIVE)
                    ).all():
                        t.status = TokenStatus.REVOKED
                        t.revoked_at = datetime.now()
                        s.add(t)
                elif isinstance(backend, SessionBackend):
                    for sess in s.exec(
                        select(Session).where(Session.user_id == user.id).where(Session.status == SessionStatus.ACTIVE)
                    ).all():

                        sess.status = SessionStatus.REVOKED
                        sess.revoked_at = datetime.now()
                        s.add(sess)

                s.commit()

            response = build_orjson_response(
                message=f"Account deactivated successfully. You can reactivate your account within {options.deletion_grace_period_days} days before it is permanently deleted.",
                base=True,
            )
            await get_backend().logout(request, response)
            return response

        @accounts_router.post(
            "/recover-account",
            status_code=status.HTTP_200_OK,
            operation_id="request_account_recovery",
            response_model=IBaseResponse,
        )
        async def request_account_recovery(
            body: Annotated[
                AuthRecoverAccountRequest,
                Body(..., description="Email to recover account for"),
            ],
        ) -> ORJSONResponse:
            """
            Request an account recovery email for a soft-deleted account.
            """
            async with db_session() as s:
                UserModel = get_user_model()
                user = (await db_exec(s, select(UserModel).where(UserModel.email == body.email))).first()

            if not user or getattr(user, "deleted_at", None) is None:
                return build_orjson_response(
                    message="If your account is eligible for recovery, an email has been sent.",
                    base=True,
                )

            token = await generate_token(kind="account_recovery", user_id=user.id)
            try:
                SendAuthEmailJob.perform_later("send_account_recovery_email", to=user.email, token=token)
            except Exception:
                logger.exception("Failed to dispatch account recovery email for %s", user.id)

            return build_orjson_response(
                message="If your account is eligible for recovery, an email has been sent.",
                base=True,
            )

        @accounts_router.get(
            "/verify-account-recovery/{token}",
            status_code=status.HTTP_200_OK,
            operation_id="verify_account_recovery",
            response_model=IBaseResponse,
        )
        async def verify_account_recovery(
            token: str = Path(..., description="Account recovery token")
        ) -> ORJSONResponse:
            """
            Verify an account recovery token and restore the soft-deleted account.
            """
            try:
                ott = await consume_token(kind="account_recovery", token=token)
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

            async with db_session() as s:
                user = (
                    await db_exec(
                        s,
                        select(get_user_model()).where(get_user_model().id == ott.user_id),
                    )
                ).first()
                if not user:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

                user.deleted_at = None
                s.add(user)
                await db_commit(s)

            return build_orjson_response(message="Account successfully recovered.", base=True)

    elif options.deletion_style == "hard":

        @accounts_router.delete(
            "/me",
            status_code=status.HTTP_200_OK,
            operation_id="delete_account_hard",
            response_model=IBaseResponse,
        )
        async def delete_account(
            request: Request,
            user: Annotated[AuthUserMixin, Depends(auth_dep)],
        ) -> ORJSONResponse:
            """
            Hard-delete the current user's account.

            Permanently removes the user and all associated sessions/tokens from the database.

            **NOTE**: It relies on cascading deletes to clean up related data setup in the database level, so make sure your database schema is set up accordingly.
            """

            async with db_session() as s:
                u = s.get(get_user_model(), user.id)
                if not u:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

                backend = get_backend()

                if isinstance(backend, JWTBackend):
                    for t in s.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).all():
                        s.delete(t)

                elif isinstance(backend, SessionBackend):
                    for sess in s.exec(select(Session).where(Session.user_id == user.id)).all():
                        s.delete(sess)

                s.delete(u)
                s.commit()

            response = build_orjson_response(
                message="Account permanently deleted successfully.",
                base=True,
            )
            await get_backend().logout(request, response)
            return response

    return accounts_router
