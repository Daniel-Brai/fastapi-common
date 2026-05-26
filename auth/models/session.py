import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import TIMESTAMP, VARCHAR, Column, Field, SQLModel

from lib.auth.enums import SessionStatus


class Session(SQLModel, table=True):
    """
    Represents a user session, created at login and consumed for every authenticated request.
    """

    __tablename__ = "auth_sessions"  # type: ignore[sqlalchemy]

    id: int = Field(primary_key=True, index=True)
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
        unique=True,
    )

    # References the user PK, no FK constraint
    user_id: int = Field(index=True)

    # Arbitrary key-value bag the app can write into (flash, device info, …)
    data: dict = Field(sa_column=Column(JSONB, nullable=False, default=dict))

    ip_address: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)

    status: SessionStatus = Field(
        sa_column=Column(VARCHAR(20), nullable=False, index=True, default=SessionStatus.ACTIVE)
    )

    created_at: datetime = Field(
        sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False, index=True)
    )
    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(timezone=True), nullable=False, index=True))
    revoked_at: datetime | None = Field(
        sa_column=Column(TIMESTAMP(timezone=True), nullable=True, index=True, default=None)
    )
