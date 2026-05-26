from sqlalchemy.orm import Session as _Session
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.jobs.config import get_adapter
from lib.jobs.schemas import JobKq

type Session = _Session | AsyncSession


class JobHandle:
    """
    A handler returned by BaseJob.perform_later() and JobProxy.perform_later().

    Calling `.with_session(session)` enlists the pending JobRecord into the
    caller's existing SQLAlchemy session so the insert commits atomically
    with the surrounding business transaction (outbox pattern).

    `.with_session()` is only meaningful on DBAdapter, on CeleryAdapter it
    is accepted silently but has no effect (the broker publish already fired).

    Usage example:

        WelcomeEmailJob.perform_later(user_id=user.id).with_session(session)

        session.commit()   # user row and job row commit together
    """

    def __init__(self, record: JobKq):
        self._record = record

    def with_session(self, session: Session) -> "JobHandle":
        adapter = get_adapter()

        from lib.jobs.adapters.db_adapter import DBAdapter

        if isinstance(adapter, DBAdapter):

            if isinstance(session, AsyncSession):
                session = session.sync_session

            adapter.enlist(self._record.id, session)

        return self
