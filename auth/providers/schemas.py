from dataclasses import dataclass, field
from typing import Any


@dataclass
class OAuthUserInfo:
    """
    Schema for normalized user info returned by OAuth providers.

    Each provider may return wildly different user info, but the library only cares about a few common fields (sub, email, name).

    Providers map their raw user-info response onto this dataclass
    """

    provider: str
    sub: str  # provider-stable user id
    email: str
    email_verified: bool = False
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None
    locale: str | None = None

    # Raw tokens from the exchange to be stored in OAuthAccount model
    access_token: str | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    token_expires_at: Any | None = None

    # Anything else the provider returns that doesn't fit above
    extra: dict[Any, Any] = field(default_factory=dict)
