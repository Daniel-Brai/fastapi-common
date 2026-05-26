import unittest
from typing import Any, Type
from unittest.mock import MagicMock

from lib.testing.notifications.utils import DeliveredCall, captured_transports


class TestNotificationCase(unittest.IsolatedAsyncioTestCase):
    """
    Base for testing a BaseNotification subclass.

    All transports are silenced via `captured_transports()` i.e nothing is sent.

    Class attributes
    ----------------
    notification_class : Type[BaseNotification]
        The concrete notification class under test. Must be set.
    """

    notification_class: Type[Any] | None = None

    async def asyncSetUp(self) -> None:
        if self.notification_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `notification_class`.")

    def make_recipient(self, **attrs: Any) -> MagicMock:
        """
        Build a mock recipient with the given attributes.
        """

        defaults = {"id": 1}
        defaults.update(attrs)

        recipient = MagicMock()
        for k, v in defaults.items():
            setattr(recipient, k, v)

        return recipient

    def captured_transports(self, *transport_classes: Type[Any]):
        """
        Helper to use `captured_transports` context manager
        """

        return captured_transports(*transport_classes)

    def assert_transport_called(
        self,
        delivered: list[DeliveredCall],
        transport_class: Type[Any],
        count: int = 1,
    ) -> None:
        matching = [d for d in delivered if d.transport_class is transport_class]
        self.assertEqual(
            len(matching),
            count,
            f"Expected {count} call(s) to {transport_class.__name__}, " f"got {len(matching)}. All: {delivered}",
        )

    def assert_transport_not_called(
        self,
        delivered: list[DeliveredCall],
        transport_class: Type[Any],
    ) -> None:
        """
        Assert that no calls were made to the given transport class in the delivered list.
        """

        self.assert_transport_called(delivered, transport_class, count=0)

    def assert_message_title(self, delivered: list[DeliveredCall], expected: str) -> None:
        """
        Assert that the message title in the first delivered call matches expected.
        """

        self.assertTrue(delivered, "No transports were called.")
        self.assertEqual(delivered[0].message.title, expected)

    def assert_message_body(self, delivered: list[DeliveredCall], expected: str) -> None:
        """
        Assert that the message body in the first delivered call matches expected.
        """

        self.assertTrue(delivered, "No transports were called.")
        self.assertEqual(delivered[0].message.body, expected)

    def assert_params_contain(self, notification: Any, **expected: Any) -> None:
        """
        Assert that `serialisable_params()` contains the given keys/values.
        """

        params = notification.serialisable_params()
        for key, value in expected.items():
            self.assertIn(key, params, f"Key {key!r} missing from serialisable_params()")
            self.assertEqual(
                params[key],
                value,
                f"serialisable_params()[{key!r}]: expected {value!r}, got {params[key]!r}",
            )

    def assert_roundtrip(self, notification: Any) -> None:
        """
        Assert that `from_params(serialisable_params())` reconstructs an equivalent notification (same type and same params).
        """

        params = notification.serialisable_params()
        reconstructed = self.notification_class.from_params(params)  # type: ignore[attr]
        self.assertIsInstance(reconstructed, self.notification_class)  # type: ignore[unreachable]
        self.assertEqual(reconstructed.serialisable_params(), params)


class TestTransportCase(unittest.IsolatedAsyncioTestCase):
    """
    Base for testing an AbstractTransport subclass in isolation.
    """

    transport_class: Type[Any] | None = None

    async def asyncSetUp(self) -> None:
        if self.transport_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `transport_class`.")
        self.transport = self.transport_class()

    def make_message(
        self,
        title: str = "Test",
        body: str = "Test body",
        url: str | None = None,
        data: dict | None = None,
    ) -> Any:
        from lib.notifications.message import NotificationMessage

        return NotificationMessage(title=title, body=body, url=url, data=data or {})

    def make_recipient(self, **attrs: Any) -> MagicMock:
        defaults: dict[str, Any] = {"id": 1}
        defaults.update(attrs)

        r = MagicMock()
        for k, v in defaults.items():
            setattr(r, k, v)

        return r

    def make_record(self, id: int = 1) -> MagicMock:
        r = MagicMock()
        r.id = id
        return r
