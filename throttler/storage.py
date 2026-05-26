from typing import Literal


class MemoryStorage:
    """
    In-process async memory storage.

    Suitable for development and single-process deployments.
    State is lost on process restart and NOT shared across workers.

    Examples
    --------

        configure_throttler(storage=MemoryStorage())
    """

    _uri = "async+memory://"

    def build(self):
        from limits.storage import storage_from_string

        return storage_from_string(self._uri)

    def __repr__(self) -> str:
        return "MemoryStorage()"


class RedisStorage:
    """
    Async Redis storage

    State persists across restarts and is shared across all worker processes,
    making it the correct choice for multi-process or multi-node deployments.

    Parameters
    ----------
    url (str)
        Redis connection URL.  Supports plain Redis or Valkey, Sentinel, and Cluster.
        Automatically prefixed with ``async+`` if not already present.

        Examples:
            "redis://localhost:6379/0"          → async+redis://...
            "valkey://host:6379/0"              → async+valkey://...
            "rediss://host:6380/0"              → async+rediss://...  (TLS)
            "redis+sentinel://host:26379/0/0"   → async+redis+sentinel://...
            "redis+cluster://host:7000"         → async+redis+cluster://...

    Options
    -------
    Keyword arguments are forwarded to ``storage_from_string`` as query
    parameters to the redis client (e.g. ``socket_timeout=1``, ``connection_pool=pool``).

    Examples
    --------

        configure_throttler(storage=RedisStorage("redis://localhost:6379/0"))
        configure_throttler(storage=RedisStorage(settings.REDIS_URL))

        # Using a custom connection pool
        import redis.asyncio as redis
        pool = redis.BlockingConnectionPool.from_url("redis://localhost:6379/0")
        configure_throttler(storage=RedisStorage("redis://localhost:6379/0", connection_pool=pool))
    """

    def __init__(
        self,
        url: str,
        impl: Literal["redispy", "coredis", "valkey"] = "redispy",
        **options,
    ) -> None:
        self._url = self._normalise(url)
        self._impl = "valkey" if url.startswith("valkey://") else impl
        self._options = options

    @staticmethod
    def _normalise(url: str) -> str:
        """
        Ensure the URL carries the async+ prefix.
        """
        if url.startswith("async+"):
            return url

        return "async+" + url

    def build(self):
        from limits.storage import storage_from_string

        return storage_from_string(self._url, implementation=self._impl, **self._options)

    def __repr__(self) -> str:
        import re

        safe = re.sub(r"://[^@]+@", "://<credentials>@", self._url)
        return f"RedisStorage({safe!r})"
