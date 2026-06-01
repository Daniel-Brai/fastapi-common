from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class EventEmitter(ABC):
    @abstractmethod
    def subscribe(self, channel: str) -> AsyncIterator[Any]: ...
    
    @abstractmethod
    async def publish(self, channel: str, message: Any) -> None: ...