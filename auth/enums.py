from enum import StrEnum


class TokenStatus(StrEnum):
    """
    Enumeration for the status of refresh tokens and sessions.

    This is used to track whether a token is active, revoked, expired, or rotated.

    Attributes:
        ACTIVE (str, "active"): The token is active and can be used for authentication.
        REVOKED (str, "revoked"): The token has been revoked and cannot be used.
        EXPIRED (str, "expired"): The token has expired and cannot be used.
        ROTATED (str, "rotated"): The token has been rotated (for refresh tokens) and cannot be used.
    """

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    ROTATED = "rotated"


class SessionStatus(StrEnum):
    """
    Enumeration for the status of user sessions.

    Attributes:
        ACTIVE (str, "active"): The session is active and can be used for authentication.
        REVOKED (str, "revoked"): The session has been revoked and cannot be used.
        EXPIRED (str, "expired"): The session has expired and cannot be used.
    """

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
