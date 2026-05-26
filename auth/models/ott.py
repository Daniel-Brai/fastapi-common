from datetime import datetime

from sqlmodel import TIMESTAMP, Column, Field, SQLModel


class OneTimeToken(SQLModel, table=True):
    """
    Represents a Single-use token record that drives every
    out-of-band auth flow: password reset, email verification, magic link and so on

    The `token_hash` column stores SHA-256(cleartext_token).

    The cleartext is only ever held in memory and sent to the user.

    Design:
        • One table (uth_one_time_tokens) with a `kind` discriminator.
        • The token value stored in the DB is a SHA-256 hash of the value sent
            to the user.  The cleartext never touches the DB (same pattern as
            password hashing so a stolen DB dump cannot replay tokens).
        • Tokens are single-use: consumed_at is set on first verification.
        • Expired and consumed tokens are never deleted automatically. The
            sweep() purges them on a schedule so forensic audit is possible.
        • The generate() classmethod returns the cleartext token for delivery
            and immediately stores the hash.

    Kinds (with example use cases):
        "password_reset"     — POST /auth/forgot-password
        "email_verification" — POST /auth/verify-email/send
        "email_change"       — POST /auth/change-email  (new address verification)
        "magic_link"         — POST /auth/magic-link
    """

    __tablename__ = "auth_one_time_tokens"  # type: ignore[sqlalchemy]

    id: int | None = Field(default=None, primary_key=True)

    # Which flow this token belongs to
    kind: str = Field(index=True)

    # SHA-256 of the cleartext value sent to the user
    token_hash: str = Field(index=True, unique=True)

    # Who the token belongs to
    user_id: int = Field(index=True)

    # For email_change: the *new* address awaiting verification
    # For email_verification: None (the user's current email is the target)
    payload: str | None = Field(default=None)

    expires_at: datetime = Field(sa_column=Column(TIMESTAMP(timezone=True), nullable=False, index=True))
    created_at: datetime = Field(
        sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False, index=True)
    )

    consumed_at: datetime | None = Field(
        sa_column=Column(
            TIMESTAMP(timezone=True),
            nullable=True,
            default=None,
        )
    )

    # Audit: IP that requested the token
    requested_from: str | None = Field(default=None)
