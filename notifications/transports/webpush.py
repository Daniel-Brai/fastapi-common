import asyncio
import json
from typing import Any

from lib.logger import get_logger
from lib.notifications.config import get_registry
from lib.notifications.message import NotificationMessage
from lib.notifications.models import Notification
from lib.notifications.schemas import PushSubscriptionType
from lib.notifications.transports.base import AbstractTransport

logger = get_logger("lib.notifications.transports.web_push")


class WebPushTransport(AbstractTransport):
    """
    Deliver a notification via the Web Push protocol (VAPID).

    Loads all push subscriptions for the recipient via the
    ``push_subscription_loader`` registered in configure_notifications(),
    then fans out one encrypted push per device concurrently.

    Expired subscriptions (HTTP 410 from the push service) are pruned
    automatically via ``push_subscription_pruner`` if registered.

    It requires :meth:`~lib.notifications.configure_notifications()` to be called with:
        - vapid_private_key
        - vapid_claims
        - push_subscription_loader

    Example::

        class NewArticleNotification(BaseNotification):
            transports = [
                DatabaseTransport(),
                SSETransport(),
                WebPushTransport(),
            ]
    """

    name = "web_push"

    async def deliver(
        self,
        message: NotificationMessage,
        recipient: Any,
        record: Notification | None,
        params: dict[str, Any] | None = None,
    ) -> None:
        try:
            from pywebpush import WebPushException, webpush
        except ImportError as exc:
            raise ImportError("WebPushTransport requires pywebpush: pip install pywebpush") from exc

        registry = get_registry()

        if registry.push_subscription_loader is None:
            logger.warning(
                "WebPushTransport: no push_subscription_loader configured — skipping. "
                "Pass push_subscription_loader= to configure_notifications()."
            )
            return

        if not registry.vapid_private_key or not registry.vapid_claims:
            logger.warning(
                "WebPushTransport: vapid_private_key or vapid_claims not configured — skipping. "
                "Pass vapid_private_key= and vapid_claims= to configure_notifications()."
            )
            return

        subscriptions: list[PushSubscriptionType] = await registry.push_subscription_loader(recipient)
        if not subscriptions:
            logger.debug(
                "WebPushTransport: no push subscriptions for recipient %s — skipping.",
                str(getattr(recipient, "id", recipient)),
            )
            return

        payload = message.to_dict()
        if record is not None:
            payload["notification_id"] = record.id

        raw_payload = json.dumps(payload)
        vapid_claims = registry.vapid_claims.to_dict()
        vapid_private_key = registry.vapid_private_key

        async def _send_one(sub: PushSubscriptionType) -> None:
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=sub.to_dict(),
                    data=raw_payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                )
                logger.debug(f"WebPushTransport: sent to {sub.endpoint}")
            except WebPushException as exc:
                if exc.response is not None and exc.response.status_code == 410:
                    logger.info(
                        f"WebPushTransport: subscription expired (410) for {sub.endpoint} will prune.",
                    )
                    raise
                logger.error(
                    f"WebPushTransport: push failed for {sub.endpoint}: {exc}",
                    exc_info=True,
                )
                if not self.fail_silently:
                    raise

        results = await asyncio.gather(
            *[_send_one(sub) for sub in subscriptions],
            return_exceptions=True,
        )

        expired_endpoints = [
            subscriptions[i].endpoint
            for i, result in enumerate(results)
            if isinstance(result, WebPushException)
            and result.response is not None
            and result.response.status_code == 410
        ]

        if expired_endpoints and registry.push_subscription_pruner is not None:
            try:
                await registry.push_subscription_pruner(recipient, expired_endpoints)
                logger.info(
                    f"WebPushTransport: pruned {len(expired_endpoints)} expired subscription(s) for recipient {str(getattr(recipient, 'id', recipient))}."
                )
            except Exception as exc:
                logger.error(
                    f"WebPushTransport: pruner failed for recipient {getattr(recipient, 'id', recipient)}: {exc}",
                    exc_info=True,
                )
