import asyncio
from weakref import WeakKeyDictionary

import redis.asyncio as redis

from .base import EventEmitter


class RedisEventEmitter(EventEmitter):
    """
    Redis backend event emitter for notifications
    """

    def __init__(
        self,
        *,
        url: str,
        **pool_kwargs,
    ):
        self._url = url
        self._pool_kwargs = pool_kwargs
        self._loop_clients: WeakKeyDictionary = WeakKeyDictionary()

    async def _get_client(self) -> redis.Redis:
        loop = asyncio.get_running_loop()
        if loop in self._loop_clients:
            return self._loop_clients[loop]

        client = redis.Redis.from_url(self._url, **self._pool_kwargs)
        self._loop_clients[loop] = client
        return client

    def subscribe(self, channel: str):
        async def gen():
            client = await self._get_client()
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)

            try:
                while True:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True)
                    if msg is None:
                        await asyncio.sleep(0.01)
                        continue

                    if msg["type"] == "message":
                        data = msg["data"]

                        if isinstance(data, bytes):
                            data = data.decode()
                        yield data
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()

        return gen()

    async def publish(self, channel: str, message: str) -> None:
        client = await self._get_client()
        await client.publish(channel, message)