
import asyncio
from typing import Any, AsyncIterator

from .base import EventEmitter


class InMemoryEventEmitter(EventEmitter):

    def __init__(self, maxsize: int | None = None):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._maxsize = maxsize

    def subscribe(self, channel: str) -> AsyncIterator[Any]:
        queue = asyncio.Queue(maxsize=self._maxsize or 0)

        async def gen():
            self._subscribers.setdefault(channel, []).append(queue)

            try:
                while True:
                    item = await queue.get()
                    yield item
            finally:
                queues = self._subscribers.get(channel)
                if queues and queue in queues:
                    queues.remove(queue)

                if not queues:
                    self._subscribers.pop(channel, None)

        return gen()

    async def publish(self, channel: str, message: Any) -> None:
        for queue in self._subscribers.get(channel, []):
            try:
                queue.put_nowait(message)
            except (asyncio.QueueFull, asyncio.QueueShutDown):
                pass
