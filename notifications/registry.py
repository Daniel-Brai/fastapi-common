from typing import Any, Callable

import redis.asyncio as redis
from lib.logger import get_logger
from lib.notifications.schemas import VAPIDClaims
from lib.notifications.types import (
    DBEngine,
    PushSubscriptionLoader,
    PushSubscriptionPruner,
)

logger = get_logger("lib.notifications.registry")


class NotificationRegistry:
    """
    Registry for notification-related configuration and dependencies.
    """

    def __init__(self) -> None:
        self._configured = False
        self.engine: DBEngine | None = None
        self._redis: redis.Redis | None = None
        self._redis_connection_pool: redis.ConnectionPool | None = None
        self._redis_connection_pool_kwargs: dict[str, Any] | None = None
        self._redis_client: redis.Redis | None = None
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
        redis: redis.Redis | None = None,
        redis_connection_pool: redis.ConnectionPool | None = None,
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
        Set configuration.  Safe to call multiple times.

        Parameters
        ----------
        engine: DBEngine | None
            SQLAlchemy Engine.  Required by DatabaseTransport.
        redis: redis.Redis | None
            Redis client instance.  Used by SSETransport.
        redis_connection_pool: redis.ConnectionPool | None
            Redis connection pool.  Used by SSETransport.
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
            Google service-account JSON file path or Credentials object.
            Required by FCMTransport.
        fcm_token_loader: Callable | None
            ``Callable(recipient) → list[str] | str | None``.
            Returns device token(s) for a recipient.
        recipient_models
            ``dict[str, type]`` — used by DeliverNotificationJob to reload
            recipients from the DB.  E.g. ``{"User": User}``.
        route_prefix: str
            Optional route prefix for the notifications API router (default: "/notifications").

        Returns
        -------
        self for chaining or storage.
        """

        self.engine = engine
        self._redis = redis
        self._redis_client = None
        self._set_redis_connection_pool(redis_connection_pool)

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

    def _set_redis_connection_pool(
        self,
        pool: redis.ConnectionPool | None,
    ) -> None:
        self._redis_connection_pool = pool
        if pool is None:
            self._redis_connection_pool_kwargs = None
            return

        self._redis_connection_pool_kwargs = {
            **pool.connection_kwargs,
            "connection_class": pool.connection_class,
            "encoder_class": pool.encoder_class,
            "max_connections": pool.max_connections,
        }

    def _create_redis_client_from_pool(self) -> redis.Redis | None:
        if self._redis_connection_pool_kwargs is None:
            return None

        try:
            pool = redis.ConnectionPool(**self._redis_connection_pool_kwargs)
            client = redis.Redis(
                connection_pool=pool,
                decode_responses=False,
            )
            logger.debug(
                "NotificationRegistry: Redis client created from connection pool"
            )
            return client
        except Exception as exc:
            logger.error(
                "NotificationRegistry: failed to create Redis client: %s",
                exc,
                exc_info=True,
            )
            return None

    @property
    def is_configured(self) -> bool:
        return self._configured

    def assert_configured(self) -> None:
        if not self._configured:
            from .exceptions import NotificationNotConfigured

            raise NotificationNotConfigured()

    @property
    def redis(self) -> redis.Redis | None:
        """
        Return the Redis client for SSE pub/sub.

        When a shared connection pool is configured, a new client is created on
        each access so it can be safely used inside the current event loop.
        """

        if self._redis_connection_pool_kwargs is not None:
            return self._create_redis_client_from_pool()
        
        if self._redis_client is None:
            self._redis_client = self._redis
            logger.debug(
                "NotificationRegistry: Redis client created from existing instance"
            )

        if self._redis is None:
            return None

        return self._redis_client

    def __repr__(self) -> str:  # pragma: no cover
        if not self._configured:
            return "NotificationRegistry(unconfigured)"

        parts = []

        if self.engine:
            parts.append(f"engine={type(self.engine).__name__}")
        if self._redis or self._redis_connection_pool:
            parts.append("redis=yes")
        if self.fcm_credentials:
            parts.append("fcm=yes")

        return f"NotificationRegistry({', '.join(parts)})"


notification_registry = NotificationRegistry()
