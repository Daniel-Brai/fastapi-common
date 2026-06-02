import asyncio
from typing import Any, AsyncIterator

import redis.asyncio as redis

from .base import EventEmitter


class RedisEventEmitter(EventEmitter):

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        connection_pool: redis.ConnectionPool | None = None,
    ):
        self._client = redis_client
        self._pool = connection_pool

    async def _get_client(self) -> redis.Redis:
        if self._client is not None:
            return self._client

        if self._pool is not None:
            return redis.Redis(connection_pool=self._pool, decode_responses=False)

        raise RuntimeError("RedisEventEmitter: no client or pool provided")

    def _owns_client(self) -> bool:
        return self._client is None and self._pool is not None

    def subscribe(self, channel: str) -> AsyncIterator[Any]:
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

                if self._owns_client():
                    await client.aclose()

        return gen()

    async def publish(self, channel: str, message: Any) -> None:
        client = await self._get_client()

        try:
            await client.publish(channel, message)
        finally:
            if self._owns_client():
                await client.aclose()
