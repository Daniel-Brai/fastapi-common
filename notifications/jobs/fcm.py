from typing import Any

from httpx import HTTPStatusError

from lib.jobs import BaseJob


class FCMNotificationJob(BaseJob):
    """
    FCM Notification Job.

    It sends a single FCM push notification and is enqueued by :class:`~lib.notifications.transports.FCMTransport`, one job per device token so failures are isolated to individual devices.
    """

    queue = "notifications"
    max_attempts = 3
    retry_on = (HTTPStatusError,)

    def perform(
        self,
        token: str,
        message: dict[str, Any],
        record_id: int | None = None,
    ) -> None:

        from lib.notifications.utils import send_fcm_push

        try:
            self.logger.info(f"FCMNotificationJob: sending FCM push with message {message}")
            send_fcm_push(token=token, message=message, record_id=record_id)
            self.logger.info("FCMNotificationJob: successfully sent FCM push")
        except HTTPStatusError as e:
            self.logger.error(f"FCMNotificationJob: failed to send FCM push with error {str(e)}")
            raise e
