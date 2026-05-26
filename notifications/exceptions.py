from typing import Any


class NotificationError(Exception):
    """
    Base exception for the notifications
    """


class NotificationNotConfigured(RuntimeError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or "Notifications are not configured. Call configure_notifications() at application startup."
        )


class RecipientMissingId(NotificationError):
    """
    Raised when a recipient object has no 'id' attribute.
    """

    def __init__(self, recipient: Any) -> None:
        super().__init__(
            f"Recipient {type(recipient).__name__!r} has no 'id' attribute. "
            "Notification recipients must have an id field."
        )


class TransportDeliveryError(NotificationError):
    """
    Raised when a transport fails to deliver and fail_silently=False.
    """

    def __init__(self, transport: str, cause: Exception) -> None:
        self.transport = transport
        self.cause = cause
        super().__init__(f"Transport {transport!r} delivery failed: {cause}")


class PushSubscriptionError(NotificationError):
    """
    Base exception for push subscription errors.
    """


class PushSubscriptionNotFoundError(PushSubscriptionError):
    """
    Raised when a subscription cannot be found.
    """


class PushSubscriptionAlreadyExistsError(PushSubscriptionError):
    """
    Raised when an endpoint is already registered.
    """
