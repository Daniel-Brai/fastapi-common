from typing import Any
from uuid import UUID

from pydantic import BaseModel, HttpUrl
from pydantic.dataclasses import dataclass

from lib.notifications.models import PushSubscription


@dataclass
class NotificationRecordResponse:
    id: int
    notification_type: str
    message: dict[str, Any]
    is_read: bool
    read_at: str | None
    created_at: str


@dataclass
class InboxResponse:
    notifications: list[NotificationRecordResponse]
    unread_count: int
    page: int
    pages: int


@dataclass
class AllNotificationsResponse:
    notifications: list[NotificationRecordResponse]
    total: int
    page: int
    pages: int


@dataclass
class MarkReadResponse:
    ok: bool = True
    read_at: str | None = None


@dataclass
class MarkAllReadResponse:
    ok: bool = True
    marked: int = 0


@dataclass
class OkResponse:
    ok: bool = True


@dataclass(frozen=True)
class PushSubscriptionKeys:
    """
    Schema for the cryptographic keys associated with a push subscription, necessary for encrypting WebPush notifications.

    Attributes:
        p256dh (str): The client's public key, encoded in Base64 URL format,
            used for encrypting the push message.
        auth (str): The authentication secret, encoded in Base64 URL format,
            used for generating the authentication tag for the push message.
    """

    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushSubscriptionType:
    """
    Schema for a push subscription, representing the necessary information to send a WebPush notification to a user's device.

    Attributes:
        endpoint (str): The URL endpoint provided by the push service (e.g., FCM
            or Safari Push Service) where the push message should be sent.
        keys (PushSubscriptionKeys): The cryptographic keys associated with the
    """

    endpoint: str
    keys: PushSubscriptionKeys

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.keys.p256dh,
                "auth": self.keys.auth,
            },
        }


@dataclass(frozen=True)
class VAPIDClaims:
    """
    Schema for VAPID claims used in WebPush notifications, as defined in RFC 8292.

    Attributes:
        sub (str): A URI (mailto: or https:) that identifies the sender of the
            push message. This is a required claim.
        aud (str | None): The origin of the push service (e.g., "https
              ://fcm.googleapis.com"). If None, pywebpush will attempt to derive
                this from the subscription endpoint. This is an optional claim.
        exp (int | None): The expiration time of the push message as a Unix
            timestamp. If None, pywebpush defaults to 12 hours from the time of
            generation. This is an optional claim.
    """

    sub: str
    aud: str | None = None
    exp: int | None = None

    def to_dict(self) -> dict[str, Any]:
        claims: dict[str, Any] = {"sub": self.sub}
        if self.aud is not None:
            claims["aud"] = self.aud
        if self.exp is not None:
            claims["exp"] = self.exp
        return claims


class RegisterPushSubscriptionRequest(BaseModel):
    """
    Schema for the request body when registering a new push subscription for a user.

    Attributes:
        endpoint (HttpUrl): The URL endpoint provided by the push service where the push message should
            be sent.
        keys (PushSubscriptionKeys): The cryptographic keys associated with the push subscription,
            necessary for encrypting WebPush notifications.
    """

    endpoint: HttpUrl
    keys: PushSubscriptionKeys


class DeletePushSubscriptionRequest(BaseModel):
    """
    Schema for the request body when unregistering a push subscription for a user.

    Attributes:
        endpoint (HttpUrl): The URL endpoint of the push subscription to be deleted.
    """

    endpoint: HttpUrl


class PushSubscriptionOut(BaseModel):
    """
    Schema for representing a push subscription in API responses.

    Attributes:
        id (UUID): The unique identifier for the push subscription.
        endpoint (HttpUrl | str): The URL endpoint provided by the push service where the push message should
            be sent.
        created_at (str): The timestamp when the push subscription was created.
    """

    id: UUID
    endpoint: HttpUrl | str
    created_at: str

    @classmethod
    def from_model(cls, subscription: PushSubscription) -> "PushSubscriptionOut":
        return cls(
            id=subscription.id,
            endpoint=subscription.endpoint,
            created_at=subscription.created_at.isoformat(),
        )
