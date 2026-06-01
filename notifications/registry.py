from typing import Any, Callable

from lib.logger import get_logger
from lib.notifications.emitter import EventEmitter, InMemoryEventEmitter
from lib.notifications.schemas import VAPIDClaims
from lib.notifications.types import DBEngine, PushSubscriptionLoader, PushSubscriptionPruner

logger = get_logger("lib.notifications.registry")


class NotificationRegistry:
    """
    Registry for notification‑related configuration and dependencies.
    """

    def __init__(self) -> None:
        self._configured = False
        self.engine: DBEngine | None = None
        self.event_emitter: EventEmitter | None = None
        self.vapid_private_key: str | None = None
        self.vapid_claims: VAPIDClaims | None = None
        self.push_subscription_loader: PushSubscriptionLoader | None = None
        self.push_subscription_pruner: PushSubscriptionPruner | None = None
        self.fcm_credentials: Any = None
        self.fcm_token_loader: Callable | None = None
        self.recipient_models: dict[str, type] = {}
        self.route_prefix = "/notifications"

    def configure_notifications(
        self,
        engine: DBEngine | None = None,
        *,
        event_emitter: EventEmitter | None = None,
        vapid_private_key: str | None = None,
        vapid_claims: VAPIDClaims | None = None,
        push_subscription_loader: PushSubscriptionLoader | None = None,
        push_subscription_pruner: PushSubscriptionPruner | None = None,
        fcm_credentials: Any = None,
        fcm_token_loader: Callable | None = None,
        recipient_models: dict[str, type] | None = None,
        route_prefix: str = "/notifications",
    ) -> "NotificationRegistry":
        """
        Set configuration. Safe to call multiple times.

        Parameters
        ----------
        engine: DBEngine | None
            SQLAlchemy Engine. Required by DatabaseTransport.
        event_emitter: EventEmitter | None
            Pub/sub backend for real time SSE notifications.
            If `None`, an **unbounded in memory** emitter is used by default.
        vapid_private_key: str | None
            VAPID private key for push notifications.
        vapid_claims: VAPIDClaims | None
            VAPID claims for push notifications.
        push_subscription_loader: PushSubscriptionLoader | None
            ``Callable(recipient) → list[PushSubscription]``.
            Returns push subscription(s) for a recipient.
        push_subscription_pruner: PushSubscriptionPruner | None
            ``Callable(recipient, tokens) → None``.
            Prunes invalid push subscription(s) for a recipient.
        fcm_credentials: Any
            Google service‑account JSON file path or Credentials object.
            Required by FCMTransport.
        fcm_token_loader: Callable | None
            ``Callable(recipient) → list[str] | str | None``.
            Returns device token(s) for a recipient.
        recipient_models
            ``dict[str, type]`` — used by DeliverNotificationJob to reload
            recipients from the DB. E.g. ``{"User": User}``.
        route_prefix: str
            Optional route prefix for the notifications API router (default: "/notifications").

        Returns
        -------
        self for chaining or storage.
        """
        self.engine = engine
        self.event_emitter = event_emitter if event_emitter is not None else InMemoryEventEmitter()
        self.vapid_private_key = vapid_private_key
        self.vapid_claims = vapid_claims
        self.push_subscription_loader = push_subscription_loader
        self.push_subscription_pruner = push_subscription_pruner
        self.fcm_credentials = fcm_credentials
        self.fcm_token_loader = fcm_token_loader
        self.recipient_models = recipient_models or {}
        self.route_prefix = route_prefix

        self._configured = True
        return self

    @property
    def is_configured(self) -> bool:
        return self._configured

    def assert_configured(self) -> None:
        if not self._configured:
            from .exceptions import NotificationNotConfigured
            raise NotificationNotConfigured()

    def __repr__(self) -> str:
        if not self._configured:
            return "NotificationRegistry(unconfigured)"
        parts = []
        if self.engine:
            parts.append(f"engine={type(self.engine).__name__}")
        if self.event_emitter:
            parts.append("event_emitter=yes")
        if self.fcm_credentials:
            parts.append("fcm=yes")
        return f"NotificationRegistry({', '.join(parts)})"


notification_registry = NotificationRegistry()