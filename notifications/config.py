from typing import Any, Callable
 
from lib.notifications.emitter import EventEmitter
from lib.notifications.registry import NotificationRegistry, notification_registry
from lib.notifications.schemas import VAPIDClaims
from lib.notifications.types import DBEngine, PushSubscriptionLoader, PushSubscriptionPruner


def configure_notifications(
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
) -> NotificationRegistry:
    """
    Wire up the notifications library. Call once in your application lifespan.

    Parameters
    ----------
    engine: DBEngine | None
        SQLAlchemy engine used by DatabaseTransport to persist notifications.
        Optional when database delivery is not used.
    event_emitter: EventEmitter | None
        Pub/sub backend for real‑time SSE notifications.
        If `None` (default), an **unbounded in‑memory** emitter is used.
        Create other emitters using:
          - `EventEmitter.from_redis(redis_client)`
          - `EventEmitter.from_redis_pool(connection_pool)`
          - `EventEmitter.memory(maxsize=...)` (bounded in‑memory)
    vapid_private_key: str | None
        VAPID private key (PEM string or path to PEM file) used by WebPushTransport for push delivery.
    vapid_claims: VAPIDClaims | None
        VAPID claims (e.g., {"sub": "mailto:example@example.com"}) used by WebPushTransport for push delivery.
    push_subscription_loader: PushSubscriptionLoader | None
        Callable that receives a recipient model instance and returns a list of push subscriptions
        (e.g., for WebPushTransport delivery).
    push_subscription_pruner: PushSubscriptionPruner | None
        Callable that receives a recipient model instance and a list of expired subscription endpoints, and prunes
        them from the data store (e.g., after receiving a 410 Gone response from a push delivery attempt).
    fcm_credentials: Any | None
        Firebase credentials object or path used by FCMTransport.
    fcm_token_loader: Callable | None
        Callable that receives a recipient model instance and returns FCM token
        values used for push delivery.
    recipient_models: dict[str, type] | None
        Mapping of model names to concrete model classes used to deserialize
        recipient references in persisted/batched deliveries.
    route_prefix: str
        Optional route prefix for the notifications API router (default: "/notifications").

    Examples
    --------
    Basic application setup with Redis:

        from lib.notifications.event_emitter import EventEmitter
        import redis.asyncio as redis

        redis_client = redis.from_url("redis://localhost")
        emitter = EventEmitter.from_redis(redis_client)

        configure_notifications(
            engine=engine,
            event_emitter=emitter,
            fcm_credentials="path/to/fcm_credentials.json",
            fcm_token_loader=lambda user: user.fcm_tokens,
            recipient_models={"User": User},
        )

    With a Redis connection pool:

        pool = redis.ConnectionPool.from_url("redis://localhost", max_connections=20)
        emitter = EventEmitter.from_redis_pool(pool)
        configure_notifications(engine=engine, event_emitter=emitter, ...)

    In memory unbounded (default, no configuration needed):

        configure_notifications(engine=engine, recipient_models={"User": User})

    In memory bounded (max 100 queued messages per subscriber):

        emitter = EventEmitter.memory(maxsize=100)
        configure_notifications(engine=engine, event_emitter=emitter, ...)

    Define a notification with multiple transports:

        from lib.notifications import BaseNotification
        from lib.notifications.transports import DatabaseTransport, FCMTransport, SSETransport

        class NewMessageNotification(BaseNotification):
            transports = [DatabaseTransport(), SSETransport(), FCMTransport()]

            def __init__(self, *, sender_name: str, text: str, channel_id: int):
                self.sender_name = sender_name
                self.text = text
                self.channel_id = channel_id

            def to_notification(self):
                from notifications.message import NotificationMessage
                return NotificationMessage(
                    title=f"New message from {self.sender_name}",
                    body=self.text[:100],
                    icon="chat-bubble",
                    url=f"/channels/{self.channel_id}",
                    data={"channel_id": self.channel_id},
                )

            def serialisable_params(self) -> dict:
                return {
                    "sender_name": self.sender_name,
                    "text": self.text,
                    "channel_id": self.channel_id,
                }

    Delivery usage:

        await NewMessageNotification(
            sender_name="Daniel", text="Hey!", channel_id=42
        ).deliver(recipient)

        NewMessageNotification(
            sender_name="Daniel", text="Hey!", channel_id=42
        ).deliver_later(recipient)

        notification = NewMessageNotification(
            sender_name="Daniel", text="Hey!", channel_id=42
        )
        await notification.deliver([user1, user2, user3])
        notification.deliver_later([user1, user2, user3])

    Notes
    -----

    Transport execution order:
        If DatabaseTransport is in `transports`, it always runs first so
        subsequent transports (SSE/WebSocket/FCM) can include the record id in
        their payloads. Remaining transports run concurrently via asyncio.gather.

    Conditional transport guards:
        ```python
        class NewMessageNotification(BaseNotification):
            transports = [
                DatabaseTransport(),
                SSETransport(),
                WebPushTransport(if_=lambda u: not u.preferences.get("allow_push_notifications", False)),
            ]
    """

    return notification_registry.configure_notifications(
        engine,
        event_emitter=event_emitter,
        vapid_private_key=vapid_private_key,
        vapid_claims=vapid_claims,
        push_subscription_loader=push_subscription_loader,
        push_subscription_pruner=push_subscription_pruner,
        fcm_credentials=fcm_credentials,
        fcm_token_loader=fcm_token_loader,
        recipient_models=recipient_models,
        route_prefix=route_prefix,
    )

def get_registry() -> NotificationRegistry:
    """
    Get the singleton NotificationRegistry instance.
    """
    notification_registry.assert_configured()
    return notification_registry

def get_router_prefix() -> str:
    """
    Get the route prefix for the notifications API router.
    """
    notification_registry.assert_configured()
    return notification_registry.route_prefix