import asyncio
from typing import Any, ClassVar

from lib.logger import get_logger
from lib.notifications.transports import AbstractTransport

logger = get_logger("lib.notifications.base")


class BaseNotification:
    """
    Base class for all notification event definitions.

    Subclass and declare:
    - ``transports`` — list of transport instances to use
    - ``to_notification()`` — build a :class:`NotificationMessage`
    - ``serialisable_params()`` — return a JSON-serialisable dict of
      constructor params (required for ``deliver_later`` and DatabaseTransport)

    Example::

        class NewMessageNotification(BaseNotification):
            transports = [
                DatabaseTransport(),
                SSETransport(),
                FCMTransport(),
            ]

            def __init__(self, *, sender_name: str, text: str, channel_id: int):
                self.sender_name = sender_name
                self.text        = text
                self.channel_id  = channel_id

            def to_notification(self) -> NotificationMessage:
                return NotificationMessage(
                    title = f"New message from {self.sender_name}",
                    body  = self.text[:100],
                    url   = f"/channels/{self.channel_id}",
                    data  = {"channel_id": self.channel_id},
                )

            def serialisable_params(self) -> dict:
                return {
                    "sender_name": self.sender_name,
                    "text":        self.text,
                    "channel_id":  self.channel_id,
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

        # Note: user1 is User in receipient_models, user2 is str id, user3 is int id all work as long as the transport's token_loader and DeliverNotificationJob can handle them.
    """

    transports: ClassVar[list[AbstractTransport]] = []

    async def deliver(self, recipients: Any) -> None:
        """
        Deliver this notification immediately to one or more recipients.

        Parameters
        ----------
        recipients
            A single recipient object or a list/iterable of recipients.

        All transports run concurrently per recipient (after DatabaseTransport,
        which always runs first if present).
        """

        if isinstance(recipients, list):
            await asyncio.gather(*[self._deliver_one(r) for r in recipients])
        else:
            await self._deliver_one(recipients)

    def deliver_later(self, recipients: Any) -> None:
        """
        Enqueue background delivery to one or more recipients via the jobs library.

        Returns immediately.  The actual transport calls happen in the worker.
        Requires ``configure_notifications(recipient_models=...)`` so the job
        can reload the recipient from the database.

        Parameters
        ----------
        recipients
            A single recipient object or a list/iterable of recipients.
        """

        targets = []
        if not isinstance(recipients, list):
            targets.append(recipients)

        from lib.notifications.jobs import DeliverNotificationJob

        notification_class = f"{type(self).__module__}.{type(self).__qualname__}"
        params = self.serialisable_params()

        for recipient in targets:
            DeliverNotificationJob.perform_later(
                notification_class=notification_class,
                recipient_type=type(recipient).__name__,
                recipient_id=str(getattr(recipient, "id", recipient)),
                params=params,
            )

    def to_notification(self) -> Any:
        """
        Build and return the :class:`NotificationMessage` for this event.

        **Must be overridden** in every concrete notification class.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement to_notification() and return " "a NotificationMessage."
        )

    def serialisable_params(self) -> dict[str, Any]:
        """
        Return a JSON-serialisable dict of this notification's constructor params.

        Required for:
          • ``deliver_later`` (serialised into the job payload)
          • DatabaseTransport (stored in ``NotificationRecord.params``)

        Override in every concrete class that uses ``deliver_later`` or
        DatabaseTransport::

            def serialisable_params(self) -> dict:
                return {"sender_name": self.sender_name, "text": self.text}
        """
        return {}

    async def _deliver_one(self, recipient: Any) -> None:
        """
        Run all transports for a single recipient.
        """

        message = self.to_notification()
        params = self.serialisable_params()
        notification_type = f"{type(self).__module__}.{type(self).__qualname__}"

        # Separate DatabaseTransport from the rest
        # it must run first so its record id is available to SSE / WS / FCM.
        db_transport = None
        other_transports = []
        for t in self.transports:
            from lib.notifications.transports.db import DatabaseTransport

            if isinstance(t, DatabaseTransport):
                db_transport = t
            else:
                other_transports.append(t)

        record = None
        if db_transport is not None:
            if db_transport.should_deliver(recipient):
                try:
                    record = await db_transport.write(
                        notification_type=notification_type,
                        message=message,
                        recipient=recipient,
                        params=params,
                    )
                except Exception as exc:
                    logger.error(
                        f"DatabaseTransport write failed for {type(recipient).__name__}: {exc}",
                        exc_info=True,
                    )
                    if not db_transport.fail_silently:
                        from lib.notifications.exceptions import TransportDeliveryError

                        raise TransportDeliveryError(db_transport.name, exc) from exc
            else:
                logger.debug(f"DatabaseTransport skipped for {type(recipient).__name__} because guard returned False.")

        if other_transports:
            await asyncio.gather(
                *[
                    self._run_transport(t, message, recipient, record, params)
                    for t in other_transports
                    if t.should_deliver(recipient)
                ]
            )

    async def _run_transport(
        self,
        transport: Any,
        message: Any,
        recipient: Any,
        record: Any,
        params: dict[str, Any],
    ) -> None:
        """
        Deliver via one transport, respecting fail_silently.
        """

        try:
            await transport.deliver(message, recipient, record, params)
        except Exception as exc:
            logger.error(
                "%s delivery failed for %s: %s",
                type(transport).__name__,
                type(recipient).__name__,
                exc,
                exc_info=True,
            )
            if not transport.fail_silently:
                from lib.notifications.exceptions import TransportDeliveryError

                raise TransportDeliveryError(transport.name, exc) from exc

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "BaseNotification":
        """
        Reconstruct a notification instance from its serialised params.

        This is called by `DeliverNotificationJob`.

        The default implementation passes all params as keyword arguments to the constructor.  Override if your
        constructor has a different signature.
        """
        return cls(**params)
