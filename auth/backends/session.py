from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Request, Response
from sqlmodel import select

from lib.auth.backends.base import AbstractBackend
from lib.auth.enums import SessionStatus
from lib.auth.exceptions import InactiveUser, NotAuthenticated, TokenExpired, TokenInvalid
from lib.auth.models import Session
from lib.ext.fastapi import get_client_ip, get_user_agent
from lib.logger import get_logger

logger = get_logger("lib.auth.backends.session")

_SESSION_COOKIE = "session_id"


class SessionBackend(AbstractBackend):
    """
    Server-side session backend.

    Attributes:
        secret_key (str): Secret key for signing session cookies.
        session_ttl (timedelta): Time-to-live for sessions.
        auto_login_on_register (bool): Whether to automatically log in users after registration and send them an email to verify their account.
        sliding (bool): Whether to refresh session expiry on each request.
        cookie_name (str): Name of the session cookie.
        secure (bool): Whether to set the Secure flag on cookies.
        samesite (str | None): SameSite attribute for cookies ("lax", "strict", "none", or None).
        httponly (bool): Whether to set the HttpOnly flag on cookies.
        path (str): Path attribute for cookies.
        domain (str | None): Domain attribute for cookies.

    Examples::

        # Basic usage with default settings:
        configure_auth(
            SessionBackend(secret_key=settings.SECRET_KEY),
        )
    """

    def __init__(
        self,
        secret_key: str,
        *,
        session_ttl: timedelta = timedelta(days=14),
        auto_login_on_register: bool = True,
        sliding: bool = True,
        cookie_name: str = _SESSION_COOKIE,
        secure: bool = True,
        samesite: Literal["lax", "strict", "none"] | None = "lax",
        httponly: bool = True,
        path: str = "/",
        domain: str | None = None,
    ):
        try:
            from itsdangerous import URLSafeTimedSerializer
        except ImportError:
            raise ImportError("pip install itsdangerous")

        self._signer = URLSafeTimedSerializer(secret_key)
        self._ttl = session_ttl
        self._sliding = sliding
        self._auto_login_on_register = auto_login_on_register
        self._cookie = cookie_name
        self._secure = secure
        self._samesite: Literal["lax", "strict", "none"] | None = samesite
        self._httponly = httponly
        self._path = path
        self._domain = domain

    def _sign(self, session_id: str) -> str:
        return self._signer.dumps(session_id)

    def _unsign(self, value: str) -> str:
        from itsdangerous import BadSignature, SignatureExpired

        try:
            return self._signer.loads(value, max_age=int(self._ttl.total_seconds()))
        except SignatureExpired:
            raise TokenExpired("Session has expired. Please log in again.")
        except BadSignature:
            raise TokenInvalid("Session is invalid. Please log in again.")

    @property
    def cookie_name(self) -> str:
        return self._cookie

    def auto_login(self) -> bool:
        return self._auto_login_on_register

    async def login(self, user, request: Request, response: Response | None, attach: bool = True) -> Session:
        record = Session(  # type: ignore[sqlmodel]
            user_id=user.id,
            expires_at=datetime.now(UTC) + self._ttl,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
        async with self._session() as s:
            await self._add_commit_refresh(s, record)

        if attach and response is not None:
            self.attach(record.session_id, response)

        logger.debug("SessionBackend: login user=%s session=%s", user.get_id(), record.session_id)
        return record

    async def logout(self, request: Request, response: Response) -> None:
        raw = request.cookies.get(self._cookie)
        if raw:
            try:
                session_id = self._unsign(raw)
                async with self._session() as s:
                    result = await self._exec(
                        s,
                        select(Session).where(Session.session_id == session_id),
                    )
                    rec = result.first()
                    if rec and rec.status == SessionStatus.ACTIVE:
                        rec.status = SessionStatus.REVOKED
                        rec.revoked_at = datetime.now(UTC)
                        s.add(rec)
                        await self._commit(s)

            except Exception as exc:
                logger.warning("SessionBackend: logout failed to revoke session: %s", exc)
                pass

        response.delete_cookie(
            self._cookie,
            path=self._path,
            domain=self._domain,
            httponly=self._httponly,
            samesite=self._samesite,
        )

    async def authenticate(self, credential: str | None):
        if credential is None:
            raise NotAuthenticated()

        session_id = self._unsign(credential)

        async with self._session() as s:
            result = await self._exec(s, select(Session).where(Session.session_id == session_id))
            rec = result.first()

            if not rec:
                raise NotAuthenticated("Session not found. Please log in again.")

            if rec and rec.status != SessionStatus.ACTIVE:
                raise NotAuthenticated("Session is no longer active. Please log in again.")

            if rec and rec.expires_at < datetime.now(UTC):
                rec.status = SessionStatus.EXPIRED
                s.add(rec)
                await self._commit(s)

                raise TokenExpired("Session has expired. Please log in again.")

            user = await self._get(s, self._user_model, rec.user_id)
            if not user:
                raise NotAuthenticated("Session not found. Please log in again.")

            if not user.is_active:
                raise InactiveUser()

            if self._sliding:
                rec.expires_at = datetime.now(UTC) + self._ttl
                s.add(rec)

            if hasattr(user, "last_login_at"):
                user.last_login_at = datetime.now(UTC)

            s.add(user)
            await self._commit(s)
            await self._refresh(s, user)

        return user

    def attach(self, credential: str, response: Response) -> None:
        response.set_cookie(
            key=self._cookie,
            value=self._sign(credential),
            max_age=int(self._ttl.total_seconds()),
            path=self._path,
            domain=self._domain,
            secure=self._secure,
            httponly=self._httponly,
            samesite=self._samesite,
        )

    async def sweep(self) -> int:
        """
        Delete sessions expired more than 24h ago.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        async with self._session() as s:
            result = await self._exec(s, select(Session).where(Session.expires_at < cutoff))
            stale = result.all()
            for rec in stale:
                await s.delete(rec)
            await self._commit(s)

        logger.info("SessionBackend: sweep deleted %d rows", len(stale))
        return len(stale)
