from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NotificationMessage:
    """
    Transport-agnostic notification payload.

    Attributes
    ----------
    title: str
        Short headline, shown in push banners, browser notifications, and
        in-app notification lists.
    body: str
        Longer description.  May be truncated by some transports.
    icon: str | None
        Icon identifier (e.g. a Lucide icon name or a URL).  Optional.
    url: str | None
        Deep-link URL the user should land on when they tap/click.  Optional.
    image_url:  str | None
        Optional image shown in rich push notifications (FCM, APNS).
    data:  dict[str, Any]
        Arbitrary extra key/value pairs forwarded to every transport as-is.
        Useful for frontend routing without URL parsing. Defaults to an empty dict.
    vibrate: list[int] | None
        Vibration pattern for mobile devices, specified as a list of durations in milliseconds.
        For example, [200, 100, 200] would vibrate for 200ms, pause for 100ms, then vibrate for another 200ms. Optional.
    require_interaction: bool
        If true, the notification will remain active until the user interacts with it, rather than automatically dismissing after a few seconds. Defaults to False.

    Each notification class should implement a `to_notification()` method that
    returns a `NotificationMessage` instance.  This is the transport-agnostic
    payload that every transport receives and formats for delivery.

    Example
    -------

    ```python
    class NewMessageNotification(BaseNotification):
        def to_notification(self) -> NotificationMessage:
            return NotificationMessage(
                title = f"New message from {self.sender.name}",
                body  = self.text[:100],
                icon  = "chat-bubble",
                url   = f"/channels/{self.channel_id}",
                data  = {"channel_id": self.channel_id},
            )
    ```
    """

    title: str
    body: str = ""
    icon: str | None = None
    url: str | None = None
    image_url: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    vibrate: list[int] | None = None
    require_interaction: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.title,
            "body": self.body,
        }
        if self.icon:
            payload["icon"] = self.icon

        if self.url:
            payload["url"] = self.url

        if self.image_url:
            payload["image_url"] = self.image_url

        if self.data:
            payload["data"] = self.data

        if self.vibrate:
            payload["vibrate"] = self.vibrate

        if self.require_interaction:
            payload["require_interaction"] = self.require_interaction

        return payload
