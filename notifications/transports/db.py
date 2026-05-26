from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.logger import get_logger
from lib.notifications.config import get_registry
from lib.notifications.message import NotificationMessage
from lib.notifications.models import Notification
from lib.notifications.transports.base import AbstractTransport

logger = get_logger("lib.notifications.transports.db")


class DatabaseTransport(AbstractTransport):
    """
    Persist a :class:`Notification` for every recipient.

    This transport always runs FIRST (the deliver loop in BaseNotification
    guarantees it) so that the record's id is available to subsequent
    transports (SSE, WebSocket) that embed it in their payload.

    The stored record can be used to:
      • Display an in-app notification inbox.
      • Track read/unread state.
      • Deep-link to the relevant object via ``record.message["url"]``.
      • Conditionally skip delayed transports if already read
        (check ``record.is_read`` inside an ``if_`` guard on other transports).

    DatabaseTransport requires that ``configure_notifications(engine=...)``
    has been called so the transport can open a session.

    Usage
    -----

        class NewMessageNotification(BaseNotification):
            transports = [DatabaseTransport(), SSETransport()]
            ...

    FastAPI inbox endpoint
    ----------------------

        @router.get("/notifications")
        def inbox(user = Depends(require_auth), session: Session = Depends(get_session)):
            stmt = (
                select(NotificationRecord)
                .where(NotificationRecord.recipient_id == str(user.id))
                .where(NotificationRecord.archived_at  == None)
                .order_by(NotificationRecord.created_at.desc())
                .limit(50)
            )
            return session.exec(stmt).all()

        @router.post("/notifications/{id}/read")
        def mark_read(id: int, session: Session = Depends(get_session)):
            record = session.get(NotificationRecord, id)
            record.mark_read(session)
            return {"ok": True}
    """

    name = "database"

    async def deliver(
        self,
        message: NotificationMessage,
        recipient: Any,
        record: Notification | None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """
        The BaseNotification.deliver loop calls _deliver_database first and passes the result to subsequent transports.

        DatabaseTransport.deliver() itself is a no-op because the record
        is created by BaseNotification._write_database_record() so the id is available before the rest of the transports run.
        """
        pass

    async def write(
        self,
        notification_type: str,
        message: NotificationMessage,
        recipient: Any,
        params: dict[str, Any],
    ) -> Any:
        """
        Write a NotificationRecord for recipient and return it.

        Called directly by BaseNotification before the transport loop so the
        record id is available to all subsequent transports.

        The configured engine may be a sync Engine or an AsyncEngine.
        """

        engine = get_registry().engine
        if engine is None:
            logger.warning(
                "DatabaseTransport: no engine configured — skipping DB write. "
                "Pass engine= to configure_notifications()."
            )
            return None

        recipient_type = type(recipient).__name__
        recipient_id = str(getattr(recipient, "id", recipient))

        rec = Notification(  # type: ignore
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            notification_type=notification_type,
            message=message.to_dict(),
            params=params or {},
        )

        if isinstance(engine, AsyncEngine):
            async_session = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with async_session() as session:
                session.add(rec)
                await session.commit()
                await session.refresh(rec)
        else:
            with Session(engine) as session:
                session.add(rec)
                session.commit()
                session.refresh(rec)

        logger.debug(
            "DatabaseTransport: wrote record #%s for %s#%s",
            rec.id,
            recipient_type,
            recipient_id,
        )
        return rec
