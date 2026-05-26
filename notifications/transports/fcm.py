from typing import Any

from lib.logger import get_logger
from lib.notifications.config import get_registry
from lib.notifications.jobs import FCMNotificationJob
from lib.notifications.transports.base import AbstractTransport

logger = get_logger("lib.notifications.transports.fcm")


class FCMTransport(AbstractTransport):
    """
    Deliver a push notification via Firebase Cloud Messaging.

    Delivery is always dispatched as a background job via the internal jobs
    library.  The actual HTTP call to the FCM v1 API happens in the worker
    process, keeping the request path fast.

    Setup
    -----

        configure_notifications(
            engine = engine,
            fcm_credentials = "/path/to/service-account.json",
            # or pass a google.oauth2.credentials.Credentials object
        )

        class NewMessageNotification(BaseNotification):
            transports = [DatabaseTransport(), SSETransport(), FCMTransport()]

    Device token registration
    -------------------------

        FCMTransport calls  notification_registry.fcm_token_loader(recipient)
        to get the device token(s).  Register your token loader at startup:

        configure_notifications(
            ...
            fcm_token_loader = lambda user: user.fcm_tokens,  # list[str] | str | None
        )

    FCM credentials
    ---------------

        FCMTransport sends via the FCM v1 HTTP API (not the legacy API).
        Credentials are a Google service account JSON file or a
        google-auth Credentials object.
    """

    name = "fcm"

    async def deliver(
        self,
        message: Any,
        recipient: Any,
        record: Any,
        params: dict[str, Any] | None = None,
    ) -> None:

        notification_registry = get_registry()

        if notification_registry.fcm_credentials is None:
            logger.warning(
                "FCMTransport: no fcm_credentials configured — skipping. "
                "Pass fcm_credentials= to configure_notifications()."
            )
            return

        token_loader = notification_registry.fcm_token_loader
        if token_loader is None:
            logger.warning(
                "FCMTransport: no fcm_token_loader configured — skipping. "
                "Register one via configure_notifications(fcm_token_loader=...)."
            )
            return

        tokens = token_loader(recipient)
        if not tokens:
            logger.debug("FCMTransport: no device tokens for recipient, skipping")
            return

        if isinstance(tokens, str):
            tokens = [tokens]

        record_id = record.id if record is not None else None

        # Enqueue a background job for each token so failures are isolated.
        for token in tokens:
            FCMNotificationJob.perform_later(
                token=token,
                message=message.to_dict(),
                record_id=record_id,
            )

        logger.debug(
            "FCMTransport: enqueued %d FCM job(s) for recipient",
            len(tokens),
        )
