import uuid
from datetime import datetime

from sqlmodel import TIMESTAMP, VARCHAR, Column, Field, SQLModel

from lib.auth.enums import TokenStatus


class RefreshToken(SQLModel, table=True):
    """
    Represents a Refresh Token record for a user session.

    The access token is short-lived and stateless, but the refresh token is long-lived and stateful.
    """

    __tablename__ = "auth_refresh_tokens"  # type: ignore[sqlalchemy]

    id: int | None = Field(default=None, primary_key=True)
    token_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
        unique=True,
    )

    # References the user PK no FK constraint; see module docstring.
    user_id: int = Field(index=True)

    # All tokens in the same family share a family_id.
    # If any token is reused after rotation, the whole family is revoked.
    family_id: str = Field(index=True)

    status: TokenStatus = Field(sa_column=Column(VARCHAR(20), nullable=False, index=True, default=TokenStatus.ACTIVE))

    ip_address: str | None = Field(default=None)
    user_agent: str | None = Field(default=None)

    issued_at: datetime = Field(
        sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False, index=True)
    )
    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(timezone=True), nullable=False, index=True))
    rotated_at: datetime | None = Field(
        sa_column=Column(TIMESTAMP(timezone=True), nullable=True, index=True, default=None)
    )
    revoked_at: datetime | None = Field(
        sa_column=Column(TIMESTAMP(timezone=True), nullable=True, index=True, default=None)
    )
