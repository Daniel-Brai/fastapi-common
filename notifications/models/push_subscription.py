from datetime import datetime
from uuid import UUID, uuid7

from sqlmodel import TIMESTAMP, Column, Field, SQLModel


class PushSubscription(
    SQLModel,
    table=True,
):
    """
    Represents a push subscription for a user, used for web push notifications.

    Attributes:
        id (UUID): The unique identifier for the push subscription.
        user_id (str): The ID of the user associated with this subscription.
        endpoint (str): The push service endpoint URL.
        p256dh (str): The client's public key for encrypting push messages.
        auth (str): The client's authentication secret for push messages.
        created_at (datetime): The timestamp when the subscription was created.
        updated_at (datetime): The timestamp when the subscription was last updated.
    """

    __tablename__ = "push_subscriptions"  # type: ignore[assignment]

    id: UUID = Field(
        default_factory=uuid7,
        primary_key=True,
        index=True,
        nullable=False,
    )
    user_id: str = Field(index=True)
    endpoint: str = Field(index=True, unique=True)
    p256dh: str
    auth: str
    created_at: datetime = Field(sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(
            TIMESTAMP(timezone=True),
            default=datetime.now,
            onupdate=datetime.now,
            nullable=False,
        )
    )
