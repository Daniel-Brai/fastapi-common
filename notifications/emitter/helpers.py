import redis.asyncio as redis

from .memory import InMemoryEventEmitter
from .redis import RedisEventEmitter

def redis_emitter_from_client(client: redis.Redis) -> RedisEventEmitter:
    """
    Create a `RedisEventEmitter` from an existing Redis client instance.

    Example usage::

        import redis.asyncio as redis
        from lib.notifications.emitter import redis_emitter_from_client

        redis_client = redis.from_url("redis://localhost")
        emitter = redis_emitter_from_client(redis_client)
        configure_notifications(engine=engine, event_emitter=emitter, ...)
    """

    return RedisEventEmitter(redis_client=client)


def redis_emitter_from_pool(pool: redis.ConnectionPool) -> RedisEventEmitter:
    """
    Create a `RedisEventEmitter` from an existing Redis connection pool.

    Example usage::

        import redis.asyncio as redis
        from lib.notifications.emitter import redis_emitter_from_pool

        pool = redis.ConnectionPool.from_url("redis://localhost", max_connections=20)
        emitter = redis_emitter_from_pool(pool)

        configure_notifications(engine=engine, event_emitter=emitter, ...)
    """

    return RedisEventEmitter(connection_pool=pool)


def in_memory_emitter(maxsize: int | None = None) -> InMemoryEventEmitter:
    """
    Create an in-memory event emitter. This is the default if no emitter is configured, but can be used explicitly if desired.

    Example usage::

        from lib.notifications.emitter import in_memory_emitter

        ## Unbounded in-memory emitter (default):
        configure_notifications(engine=engine, recipient_models={"User": User})

        ## Bounded in-memory emitter with max 100 queued messages per subscriber:
        
        emitter = in_memory_emitter(maxsize=100)
        configure_notifications(engine=engine, event_emitter=emitter, ...)
    """

    return InMemoryEventEmitter(maxsize=maxsize)