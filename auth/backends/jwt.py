import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel import col, select

from lib.auth.backends.base import AbstractBackend
from lib.auth.enums import TokenStatus
from lib.auth.exceptions import (
    InactiveUser,
    NotAuthenticated,
    RefreshTokenReuse,
    TokenExpired,
    TokenInvalid,
    TokenRevoked,
)
from lib.auth.models import RefreshToken
from lib.auth.token import AccessTokenClaims, RefreshTokenClaims, TokenCodec, TokenPair
from lib.ext.fastapi import get_client_ip, get_user_agent
from lib.logger import get_logger

logger = get_logger("lib.auth.backends.jwt")

_REFRESH_COOKIE = "refresh_token"


class JWTBackend(AbstractBackend):
    """
    Stateful JWT backend with access and refresh tokens, token rotation, and family revocation.

    Attributes:
        codec (TokenCodec): TokenCodec instance for encoding/decoding JWTs.
        access_ttl (timedelta): Time-to-live for access tokens.
        refresh_ttl (timedelta): Time-to-live for refresh tokens.
        refresh_cookie (str): Name of the cookie to store the refresh token.
        auto_login_on_register (bool): Whether to automatically log in users after registration and send them an email to verify their account.
        refresh_in_body (bool): Whether to return the refresh token in the response body on login/refresh.
        secure (bool): Whether to set the Secure flag on cookies.
        samesite (str | None): SameSite policy for cookies ("lax", "strict", "none", or None to omit).
        path (str): Path attribute for cookies.
        domain (str | None): Domain attribute for cookies.

    Examples::

        configure_auth(JWTBackend(codec=TokenCodec(secret=settings.JWT_SECRET)))

    """

    def __init__(
        self,
        codec: TokenCodec,
        *,
        access_ttl: timedelta = timedelta(minutes=15),
        refresh_ttl: timedelta = timedelta(days=7),
        refresh_cookie: str = _REFRESH_COOKIE,
        auto_login_on_register: bool = True,
        refresh_in_body: bool = False,
        secure: bool = True,
        samesite: Literal["lax", "strict", "none"] | None = "lax",
        path: str = "/",
        domain: str | None = None,
    ) -> None:
        self._codec = codec
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._refresh_cookie = refresh_cookie
        self._refresh_in_body = refresh_in_body
        self._auto_login_on_register = auto_login_on_register
        self._secure = secure
        self._samesite: Literal["lax", "strict", "none"] | None = samesite
        self._path = path
        self._domain = domain

    async def _issue_pair(
        self,
        user,
        request: Request,
        family_id: str | None = None,
    ) -> tuple[TokenPair, RefreshToken]:

        fid = family_id or str(uuid.uuid4())
        jti = str(uuid.uuid4())
        roles = list(getattr(user, "roles", None) or [])
        email = str(getattr(user, "email", ""))

        access_claims = AccessTokenClaims(sub=user.get_id(), email=email, roles=roles)
        refresh_claims = RefreshTokenClaims(sub=user.get_id(), jti=jti, fid=fid)

        access_token = self._codec.make_access_token(access_claims, self._access_ttl)
        refresh_token = self._codec.make_refresh_token(refresh_claims, self._refresh_ttl)

        record = RefreshToken(  # type: ignore[assignment]
            token_id=jti,
            user_id=user.id,
            family_id=fid,
            expires_at=datetime.now(UTC) + self._refresh_ttl,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        async with self._session() as s:
            await self._add_commit_refresh(s, record)

        pair = TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self._access_ttl.total_seconds()),
        )
        return pair, record

    def auto_login(self) -> bool:
        return self._auto_login_on_register

    async def login(self, user, request: Request, response: Response | None, attach: bool = True) -> TokenPair:
        pair, _ = await self._issue_pair(user, request)

        if attach and response is not None:
            self.attach(pair, response)

        async with self._session() as s:
            u = await self._get(s, self._user_model, user.id)
            if u and hasattr(u, "last_login_at"):
                u.last_login_at = datetime.now(UTC)
                s.add(u)
                await self._commit(s)

        logger.debug("JWTBackend: JWT login user=%s", user.get_id())
        return pair

    async def logout(self, request: Request, response: Response) -> None:
        raw = request.cookies.get(self._refresh_cookie)
        if raw:
            try:
                claims = self._codec.decode_refresh(raw)
                async with self._session() as s:
                    result = await self._exec(
                        s,
                        select(RefreshToken)
                        .where(col(RefreshToken.family_id) == claims.fid)
                        .where(col(RefreshToken.status) == TokenStatus.ACTIVE),
                    )
                    family = result.all()
                    for rec in family:
                        rec.status = TokenStatus.REVOKED
                        rec.revoked_at = datetime.now(UTC)
                        s.add(rec)

                    await self._commit(s)
                    logger.info(
                        "JWTBackend: logout revoked %d token(s) in family %s",
                        len(family),
                        claims.fid,
                    )
            except Exception as exc:
                logger.warning("JWTBackend: logout error: %s", exc)
                pass

        response.delete_cookie(
            self._refresh_cookie,
            path=self._path,
            domain=self._domain,
            httponly=True,
            samesite=self._samesite,
        )

    async def refresh(self, request: Request, response: Response | None, attach: bool = True) -> TokenPair:
        """
        Rotate the refresh token.

        Reuse of a rotated token triggers full family revocation (theft response).
        """

        raw = request.cookies.get(self._refresh_cookie) or self._bearer_token(request)
        if not raw:
            raise NotAuthenticated("No refresh token provided")

        try:
            claims = self._codec.decode_refresh(raw)
        except Exception as exc:
            raise TokenInvalid(str(exc)) from exc

        async with self._session() as s:
            result = await self._exec(
                s,
                select(RefreshToken).where(RefreshToken.token_id == claims.jti),
            )
            rec = result.first()

            if not rec:
                raise TokenInvalid("Refresh token not found")

            if rec.status == TokenStatus.ROTATED:
                family_result = await self._exec(
                    s,
                    select(RefreshToken).where(RefreshToken.family_id == claims.fid),
                )
                for r in family_result.all():
                    r.status = TokenStatus.REVOKED
                    r.revoked_at = datetime.now(UTC)
                    s.add(r)
                await self._commit(s)

                logger.warning("Refresh token reuse — revoked family %s", claims.fid)
                raise RefreshTokenReuse()

            if rec.status in (TokenStatus.REVOKED, TokenStatus.EXPIRED):
                raise TokenRevoked()

            if rec.expires_at < datetime.now(UTC):
                rec.status = TokenStatus.EXPIRED
                s.add(rec)
                await self._commit(s)
                raise TokenExpired("Refresh token has expired")

            user = await self._get(s, self._user_model, rec.user_id)
            if not user or not user.is_active:
                raise InactiveUser()

            rec.status = TokenStatus.ROTATED
            rec.rotated_at = datetime.now(UTC)
            s.add(rec)

            await self._commit(s)

        pair, _ = await self._issue_pair(user, request, family_id=claims.fid)

        if attach and response is not None:
            self.attach(pair, response)

        logger.debug("JWTBackend: refresh user=%s family=%s", user.get_id(), claims.fid)
        return pair

    async def authenticate(self, credential: HTTPAuthorizationCredentials | None):
        """
        Validate the access token from Authorization: Bearer.
        """

        if not credential:
            raise NotAuthenticated("No credentials provided")

        token = credential.credentials
        if not token:
            raise NotAuthenticated()

        try:
            claims = self._codec.decode_access(token)
        except Exception as exc:
            if "expired" in str(exc).lower():
                raise TokenExpired()

            raise TokenInvalid(str(exc)) from exc

        UserModel = self._user_model

        async with self._session() as s:
            if hasattr(UserModel, "uuid"):
                result = await self._exec(
                    s, select(UserModel).where(UserModel.uuid == claims.sub)  # type: ignore[attr-defined]
                )
                user = result.first()
            else:
                try:
                    pk = int(claims.sub)
                except (ValueError, TypeError):
                    pk = claims.sub
                user = await self._get(s, UserModel, pk)

        if not user:
            raise NotAuthenticated("Account not found. Please sign up to continue.")

        if not user.is_active:
            raise InactiveUser()

        return user

    def attach(self, credential: TokenPair, response: Response) -> None:
        response.set_cookie(
            key=self._refresh_cookie,
            value=credential.refresh_token,
            max_age=int(self._refresh_ttl.total_seconds()),
            path=self._path,
            domain=self._domain,
            secure=self._secure,
            httponly=True,
            samesite=self._samesite,  # type: ignore[arg-type]
        )

    @staticmethod
    def _bearer_token(request: Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:]

        return None

    async def sweep(self) -> int:
        """
        Delete expired/rotated/revoked refresh tokens older than 24h.
        """

        cutoff = datetime.now(UTC) - timedelta(hours=24)
        async with self._session() as s:
            result = await self._exec(
                s,
                select(RefreshToken)
                .where(
                    col(RefreshToken.status).in_(
                        [
                            TokenStatus.EXPIRED,
                            TokenStatus.ROTATED,
                            TokenStatus.REVOKED,
                        ]
                    )
                )
                .where(col(RefreshToken.expires_at) < cutoff),
            )
            old = result.all()
            for rec in old:
                s.delete(rec)

            await self._commit(s)

        logger.info("JWTBackend: Sweep deleted %d refresh token(s)", len(old))

        return len(old)
