from typing import Any

from lib.cache.service import Cache


async def get_cache_service(
    redis: Any = None, redis_connection_pool: Any = None, namespace: str = "default", use_orjson: bool = False
) -> Cache:
    """
    A factory function that creates and returns a `Cache` instance.

    Example usage:

    ```python
    from redis.asyncio import Redis
    from lib.cache.config import get_cache_service

    async def main():
        redis = Redis(host='localhost', port=6379, db=0)
        cache_service = await get_cache_service(redis, namespace="my_app")
        # Now you can use cache_service to interact with the cache
    ```
    """

    return Cache(redis, redis_connection_pool, namespace=namespace, use_orjson=use_orjson)
