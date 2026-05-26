from dataclasses import dataclass
from typing import Any, Type


@dataclass
class DeliveredCall:
    """
    A class that records a single `deliver()` call intercepted by `captured_transports()`.

    Attributes
    ----------
        transport_class (type[AbstractTransport]) : the AbstractTransport subclass
        message (NotificationMessage) : NotificationMessage passed to deliver()
        recipient (Any) : recipient object
        record (Any) : Notification DB record (or None)
        params (dict[str, Any]) : serialisable_params dict
    """

    transport_class: Type[Any]
    message: Any
    recipient: Any
    record: Any
    params: dict[str, Any]

    def __repr__(self) -> str:
        return (
            f"<DeliveredCall {self.transport_class.__name__} "
            f"recipient={getattr(self.recipient, 'id', self.recipient)!r}>"
        )
