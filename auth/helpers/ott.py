import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import select

from lib.auth.exceptions import TokenExpired, TokenInvalid, TokenRevoked
from lib.auth.helpers.db import db_commit, db_exec, db_refresh, db_session
from lib.auth.models.ott import OneTimeToken

_DEFAULT_TTL: dict[str, timedelta] = {
    "password_reset": timedelta(hours=1),
    "email_verification": timedelta(hours=24),
    "email_change": timedelta(hours=24),
    "magic_link": timedelta(minutes=15),
}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def generate_token(
    *,
    kind: str,
    user_id: Any,
    payload: str | None = None,
    ttl: timedelta | None = None,
    requested_from: str | None = None,
) -> str:
    """
    Generate a cryptographically-random token, store its hash, return cleartext.

    The caller delivers the cleartext to the user (email, SMS).

    It is never stored, only SHA-256(cleartext) is persisted.
    """

    effective_ttl = ttl or _DEFAULT_TTL.get(kind, timedelta(hours=1))
    cleartext = secrets.token_urlsafe(32)

    record = OneTimeToken(  # type: ignore[assignment]
        kind=kind,
        token_hash=_hash(cleartext),
        user_id=user_id,
        payload=payload,
        expires_at=datetime.now() + effective_ttl,
        requested_from=requested_from,
    )

    async with db_session() as s:
        result = await db_exec(
            s,
            select(OneTimeToken)
            .where(OneTimeToken.kind == kind)
            .where(OneTimeToken.user_id == user_id)
            .where(OneTimeToken.consumed_at == None),  # noqa: E711
        )
        for old in result.all():
            s.delete(old)

        s.add(record)
        await db_commit(s)

    return cleartext


async def consume_token(
    *,
    kind: str,
    token: str,
) -> OneTimeToken:
    """
    Validate and consume a one-time token.

    Returns the OneTimeToken record on success.

    Raises TokenInvalid / TokenRevoked / TokenExpired on failure.
    The record's consumed_at is stamped such that subsequent calls fail.
    """

    h = _hash(token)

    async with db_session() as s:
        result = await db_exec(
            s,
            select(OneTimeToken).where(OneTimeToken.token_hash == h).where(OneTimeToken.kind == kind),
        )
        rec = result.first()

        if not rec:
            raise TokenInvalid(f"Invalid {kind} token")

        if rec.consumed_at is not None:
            raise TokenRevoked(f"{kind} token has already been used")

        if rec.expires_at < datetime.now():
            raise TokenExpired(f"{kind} token has expired")

        rec.consumed_at = datetime.now()
        s.add(rec)
        await db_commit(s)
        await db_refresh(s, rec)
        return rec


async def sweep_tokens(*, grace: timedelta = timedelta(hours=24)) -> int:
    """
    Delete tokens that expired more than `grace` ago.
    """

    cutoff = datetime.now() - grace

    async with db_session() as s:
        result = await db_exec(s, select(OneTimeToken).where(OneTimeToken.expires_at < cutoff))
        old = result.all()
        for rec in old:
            s.delete(rec)

        await db_commit(s)

    return len(old)
