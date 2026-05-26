from abc import ABC, abstractmethod
from typing import Any, Callable

from lib.logger import get_logger
from lib.notifications.message import NotificationMessage
from lib.notifications.models import Notification

logger = get_logger("lib.notifications.transports.base")


class AbstractTransport(ABC):
    """
    Base class for all notification transports.

    Every transport receives a :class:`NotificationMessage` and the recipient
    object, then delivers it in whatever way makes sense for that channel.

    Attributes
    ----------
    name: str
        Short identifier used in logs and job serialisation.
    fail_silently: bool
        When True (default), delivery errors are logged but not re-raised.
        Set to False in tests or for critical transports.
    **if_**: Callable[[Any], bool] | None
        Optional guard called with the recipient instance. Delivery only
        proceeds if this returns True.
    """

    name: str = "base"
    fail_silently: bool = True
    if_: Callable[[Any], bool] | None = None

    def __init__(self, *, if_: Callable[[Any], bool] | None = None, fail_silently: bool = True) -> None:
        self.if_ = if_
        self.fail_silently = fail_silently

    def should_deliver(self, recipient: Any) -> bool:
        if self.if_ is None:
            return True

        try:
            return self.if_(recipient)
        except Exception as exc:
            logger.error(
                f"Transport guard evaluation failed for {type(recipient).__name__}  recipient {exc}",
                exc_info=True,
            )
            return False

    @abstractmethod
    async def deliver(
        self,
        message: NotificationMessage,
        recipient: Any,
        record: Notification | None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """
        Deliver the notification through this transport.

        Parameters
        ----------
        message: str
            The transport-agnostic payload produced by the notification.
        recipient: Any
            The user / model instance being notified.
        record: Notification | None
            The :class:`Notification` written by DatabaseTransport,
            or None if that transport has not run yet (or is not in use).
            Transports that embed a record ID in their payload (e.g. for
            frontend deep-linking) should check for None.
        params: dict[str, Any]
            The notification's serialisable params dict, useful for
            transports that need the raw event data.
        """
        raise NotImplementedError("Subclasses must implement deliver()")
