from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.notifications.models import Notification
from lib.notifications.schemas import NotificationRecordResponse


async def get_own_record(
    notification_id: int,
    user: Any,
    session: AsyncSession | Session,
) -> Notification | None:
    if isinstance(session, AsyncSession):
        record = await session.get(Notification, notification_id)
    else:
        record = session.get(Notification, notification_id)

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if record.recipient_id != str(user.id) or record.recipient_type != type(user).__name__:
        return None

    return record


def serialise_record(record: Any) -> NotificationRecordResponse:
    return NotificationRecordResponse(
        id=record.id,
        notification_type=record.notification_type.rsplit(".", 1)[-1],
        message=record.message,
        is_read=record.is_read,
        read_at=record.read_at.isoformat() if record.read_at else None,
        created_at=record.created_at.isoformat(),
    )
