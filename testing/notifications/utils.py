from contextlib import contextmanager
from typing import Any, Generator, Type
from unittest.mock import patch

from lib.testing.notifications.types import DeliveredCall


@contextmanager
def captured_transports(
    *transport_classes: Type[Any],
) -> Generator[list[DeliveredCall], None, None]:
    """
    A context manager to intercept `deliver()` calls on the given transport classes so nothing is actually
    sent.

    It records every call as a `DeliveredCall` for assertion.

    Example
    -------
        ```python
        with captured_transports(SSETransport, WebPushTransport) as delivered:
            await notification.deliver(user)

        assert len(delivered) == 2
        sse_call = next(d for d in delivered if d.transport_class is SSETransport)
        assert sse_call.recipient is user
        assert sse_call.message.title == "Fresh reads waiting"
        ```
    """

    sink: list[DeliveredCall] = []

    patches = []
    for cls in transport_classes:

        async def _capturing_deliver(
            self_transport,  # noqa: ARG001
            message,
            recipient,
            record=None,
            params=None,
            *,
            _cls=cls,
        ):
            sink.append(
                DeliveredCall(
                    transport_class=_cls,
                    message=message,
                    recipient=recipient,
                    record=record,
                    params=params or {},
                )
            )

        patches.append(patch.object(cls, "deliver", _capturing_deliver))

    for p in patches:
        p.start()

    try:
        yield sink
    finally:
        for p in patches:
            p.stop()


def mock_notification(
    transports: list[Any] | None = None,
    title: str = "Test Notification",
    body: str = "Test body",
) -> Any:
    """
    Build a minimal concrete `BaseNotification` for testing a transport
    directly without a real notification class.

    Usage:

        notif = mock_notification(transports=[SSETransport()])
        await notif.deliver(user)
    """

    from lib.notifications.base import BaseNotification
    from lib.notifications.message import NotificationMessage

    class MockNotification(BaseNotification):
        pass

    MockNotification.transports = transports or []

    instance = MockNotification.__new__(MockNotification)
    message = NotificationMessage(title=title, body=body)
    instance.to_notification = lambda: message
    instance.serialisable_params = lambda: {"title": title, "body": body}
    return instance
