import json
from typing import Any

from lib.logger import get_logger
from lib.notifications.config import get_registry
from lib.notifications.constants import SSE_CHANNEL_PREFIX
from lib.notifications.message import NotificationMessage
from lib.notifications.transports.base import AbstractTransport
from lib.notifications.utils import channel_key

logger = get_logger("lib.notifications.transports.sse")


class SSETransport(AbstractTransport):
    """
    Deliver a notification as an SSE event by publishing JSON to Redis.

    Any open SSE stream for the recipient will receive the event in real time.
    If no stream is open, the message is dropped; SSE is fire-and-forget.

    Use this transport together with DatabaseTransport so recipients can fetch
    missed notifications when they reconnect.

    Requires configure_notifications(event_emitter=...) to provide an EventEmitter.

    Examples:

        from lib.notifications.router import make_sse_router
        app.include_router(make_sse_router(), prefix="/notifications")

        # Or wire your own stream endpoint:
        from lib.notifications.utils import subscribe_sse

        @router.get("/notifications/stream")
        async def stream(user=Depends(make_auth_dependency(get_backend()))):
            return EventSourceResponse(subscribe_sse(user.id, get_registry().event_emitter))
    """

    name = "sse"

    async def deliver(
        self,
        message: NotificationMessage,
        recipient: Any,
        record: Any = None,
        params: dict[str, Any] | None = None,
    ) -> None:

        event_emitter = get_registry().event_emitter
        if event_emitter is None:
            logger.warning(
                "SSETransport: no event emitter configured — skipping. "
                "Pass event_emitter= to configure_notifications()."
            )
            return

        recipient_id = str(getattr(recipient, "id", recipient))
        channel = channel_key(SSE_CHANNEL_PREFIX, recipient_id)

        payload = message.to_dict()
        if record is not None:
            payload["notification_id"] = record.id

        try:
            await event_emitter.publish(channel, json.dumps(payload))
            logger.debug("SSETransport: published to %s", channel)
        except Exception as exc:
            logger.error("SSETransport: publish failed: %s", exc, exc_info=True)
            if not self.fail_silently:
                raise exc
