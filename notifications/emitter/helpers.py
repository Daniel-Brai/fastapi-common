import redis.asyncio as redis

from .memory import InMemoryEventEmitter
from .redis import RedisEventEmitter


def redis_emitter_from_url(url: str, **pool_kwargs) -> RedisEventEmitter:
    """
    Create a RedisEventEmitter that can safely be used from any event loop.

    This is the recommended way to configure Redis-based SSE notifications.

    Example usage::

        from lib.notifications.emitter import redis_emitter_from_url

        event_emitter = redis_emitter_from_url(
            str(settings.APP_REDIS_URL),
            max_connections=20,
            socket_timeout=10.0,
            socket_connect_timeout=10.0,
            health_check_interval=30,
            retry=Retry(...),
            decode_responses=False,
        )

        configure_notifications(engine=engine, event_emitter=event_emitter, ...)
    """

    return RedisEventEmitter(url=url, **pool_kwargs)



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