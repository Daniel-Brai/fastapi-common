import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Generator

_auditor: ContextVar[Any | None] = ContextVar("audit_auditor", default=None)
_comment: ContextVar[str | None] = ContextVar("audit_comment", default=None)
_request_id: ContextVar[str | None] = ContextVar("audit_request_uuid", default=None)
_remote_addr: ContextVar[str | None] = ContextVar("audit_remote_addr", default=None)


def set_auditor(user: Any) -> None:
    """
    Set the current auditor for this async context / thread.
    Usually called by AuditMiddleware on each request.

        set_auditor(current_user)   # user model instance
        set_auditor(None)           # system / background task
    """
    _auditor.set(user)


def set_request_id(request_uuid: str | None = None) -> str:
    """
    Set (or generate) a UUID for the current request.

    Returns the id that was set.
    """
    uid = request_uuid or str(uuid.uuid4())
    _request_id.set(uid)
    return uid


def set_remote_addr(addr: str | None) -> None:
    """
    Set the client IP address for the current request.
    """
    _remote_addr.set(addr)


def get_auditor() -> Any | None:
    """
    Return the current auditor (user model instance or None).
    """
    return _auditor.get()


def get_comment() -> str | None:
    """
    Return the current audit comment or None.
    """
    return _comment.get()


def get_request_id() -> str | None:
    """
    Return the current request id or None.
    """
    return _request_id.get()


def get_remote_addr() -> str | None:
    """
    Return the current client IP or None.
    """
    return _remote_addr.get()


@contextmanager
def audit_comment(comment: str) -> Generator[None, None, None]:
    """
    Sync context manager: annotate a block of DB changes with a comment.

    Example:

        with audit_comment("Bulk import from admin panel"):
            for row in csv_rows:
                session.add(Post(**row))
            session.commit()
    """
    token = _comment.set(comment)
    try:
        yield
    finally:
        _comment.reset(token)


@asynccontextmanager
async def async_audit_comment(comment: str) -> AsyncIterator[None]:
    """
    Async context manager: annotate a block of async DB changes with a comment.

    Example:

        async with async_audit_comment("Admin correction"):
            user.email = new_email
            await session.commit()
    """
    token = _comment.set(comment)
    try:
        yield
    finally:
        _comment.reset(token)
