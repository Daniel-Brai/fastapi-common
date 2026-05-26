from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlmodel import TIMESTAMP, Column, Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class Notification(SQLModel, table=True):
    """
    Represents a single notification to be delivered to a user.

    Attributes:
        id (int): The unique identifier for the notification.
        recipient_type (str): The type of recipient (e.g., "User", "Organization
        recipient_id (str): The ID of the recipient (stringified PK).
        notification_type (str): The fully-qualified class name of the notification (e.g., "app.notifications.NewMessageNotification").
        message (dict): A snapshot of the notification message at delivery time.
        params (dict): A snapshot of the notification's serialisable params at delivery time.
        read_at (datetime | None): The timestamp when the notification was marked as read, or
            None if it is unread.
        archived_at (datetime | None): The timestamp when the notification was archived, or
            None if it is not archived.
        created_at (datetime): The timestamp when the notification was created.
    """

    __tablename__ = "notifications"  # type: ignore[assignment]

    id: int = Field(primary_key=True)

    recipient_type: str = Field(index=True)
    recipient_id: str = Field(index=True)

    notification_type: str = Field(index=True)

    message: dict[Any, Any] = Field(sa_column=Column(JSONB(), default=dict))

    params: dict[Any, Any] = Field(sa_column=Column(JSONB(), default=dict))

    read_at: datetime | None = Field(sa_column=Column(TIMESTAMP(timezone=True), default=None, index=True))
    archived_at: datetime | None = Field(sa_column=Column(TIMESTAMP(timezone=True), default=None))
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False))

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def is_unread(self) -> bool:
        return self.read_at is None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def recipient_label(self) -> str:
        return f"{self.recipient_type}#{self.recipient_id}"

    async def mark_read(self, session: Session | AsyncSession) -> None:
        """
        Mark this notification as read and persist immediately.
        """

        if self.read_at is None:
            self.read_at = datetime.now()
            session.add(self)

            if isinstance(session, AsyncSession):
                await session.commit()
            else:
                session.commit()

    async def mark_unread(self, session: Session | AsyncSession) -> None:
        """
        Unmark this notification as read.
        """

        if self.read_at is not None:
            self.read_at = None
            session.add(self)

            if isinstance(session, AsyncSession):
                await session.commit()
            else:
                session.commit()

    async def archive(self, session: Session | AsyncSession) -> None:
        """
        Archive this notification (hide from inbox).
        """

        if self.archived_at is None:
            self.archived_at = datetime.now()

            session.add(self)

            if isinstance(session, AsyncSession):
                await session.commit()
            else:
                session.commit()

    def __repr__(self) -> str:  # pragma: no cover
        status = "read" if self.is_read else "unread"
        return (
            f"<Notification #{self.id} "
            f"{self.notification_type.rsplit('.', 1)[-1]} "
            f"→ {self.recipient_label} [{status}]>"
        )
