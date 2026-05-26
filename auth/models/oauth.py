from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import TIMESTAMP, Column, Field, SQLModel


class OAuthAccount(SQLModel, table=True):
    """
    Represents a user's linked OAuth account (e.g. "Sign in with Google").
    """

    __tablename__ = "auth_oauth_accounts"  # type: ignore[sqlalchemy]

    id: int = Field(primary_key=True, index=True)

    # References the user PK, no FK constraint; see module docstring.
    user_id: int = Field(index=True)

    provider: str = Field(index=True)  # "google", "apple" and so on
    provider_sub: str = Field(index=True)  # provider's stable user id
    email: str | None = Field(default=None)  # as reported by provider

    # Raw tokens from the last OAuth exchange
    access_token: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    id_token: str | None = Field(default=None)
    token_expires_at: datetime | None = Field(default=None)

    # Extra provider data (avatar_url, locale, real_user_status, and so on)
    extra: dict[Any, Any] = Field(sa_column=Column(JSONB(), default=dict))

    created_at: datetime = Field(sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False))

    updated_at: datetime | None = Field(
        sa_column=Column(
            TIMESTAMP(timezone=True),
            default=None,
            nullable=True,
            onupdate=datetime.now,
        )
    )
