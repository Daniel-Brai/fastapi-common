import redis.asyncio as redis

from .memory import InMemoryEventEmitter
from .redis import RedisEventEmitter

def redis_emitter_from_client(client: redis.Redis) -> RedisEventEmitter:
    return RedisEventEmitter(redis_client=client)


def redis_emitter_from_pool(pool: redis.ConnectionPool) -> RedisEventEmitter:
    return RedisEventEmitter(connection_pool=pool)


def in_memory_emitter(maxsize: int | None = None) -> InMemoryEventEmitter:
    return InMemoryEventEmitter(maxsize=maxsize)