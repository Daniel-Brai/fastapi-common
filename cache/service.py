import json
from collections.abc import Awaitable, Callable
from typing import Any

import orjson
from pydantic import TypeAdapter
from redis.asyncio import ConnectionPool, Redis

from lib.cache.exceptions import CacheNotConfigured
from lib.cache.utils import build_cache_key, get_ttl_with_jitter
from lib.logger import get_logger

logger = get_logger("lib.cache.service")


class Cache[T: Any]:
    """
    Generic async Redis cache service with automatic serialization.

    Examples:

        user_cache = Cache[User](
            redis=redis_client,
            namespace="users",
            model=User,
            default_ttl=600,
        )

        user = await user_cache.get("123")

        await user_cache.set("123", user)

    Tuple example:

        event_cache = Cache[
            tuple[str, User | None, str | None]
        ](
            redis=redis_client,
            namespace="events",
            model=tuple[str, User | None, str | None],
        )

        await event_cache.set(
            "event:1",
            (
                "user.created",
                user,
                None,
            ),
        )
    """

    def __init__(
        self,
        redis: Redis | None = None,
        redis_connection_pool: ConnectionPool | None = None,
        namespace: str = "default",
        model: type[T] | Any | None = None,
        default_ttl: int = 300,
        use_jitter: bool = True,
        use_orjson: bool = False,
        prefix: str = "cache",
        version: str = "v1",
    ):
        """
        Initialize cache service.

        Args:
            redis (Redis | None):
                Existing Redis client instance.

            redis_connection_pool (ConnectionPool | None):
                Redis connection pool used to lazily create a client.

            namespace (str):
                Cache namespace used for key grouping.

            model (type[T] | Any | None):
                Type used for deserialization when retrieving cached data.

            default_ttl (int):
                Default cache TTL in seconds.

            use_jitter (bool):
                Whether to apply randomized TTL jitter.

            use_orjson (bool):
                Whether to use orjson for faster serialization.

            prefix (str):
                Global cache key prefix.

            version (str):
                Cache key version namespace.
        """

        self.redis = redis
        self.redis_connection_pool = redis_connection_pool
        self.namespace = namespace
        self.model = model
        self.default_ttl = default_ttl
        self.use_jitter = use_jitter
        self.use_orjson = use_orjson
        self.prefix = prefix
        self.version = version

        self._assert_redis()

    def _assert_redis(self):
        """
        Ensure Redis configuration exists.
        """

        if self.redis is None and self.redis_connection_pool is None:
            raise CacheNotConfigured()

    def _build_key(
        self,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a namespaced cache key.

        Args:
            identifier (str):
                Unique cache identifier.

            params (dict[str, Any] | None):
                Optional key parameters.

        Returns:
            str:
                Fully qualified cache key.
        """

        return build_cache_key(
            self.namespace,
            identifier,
            params,
            prefix=self.prefix,
            version=self.version,
        )

    def _get_ttl(self, ttl: int | None = None) -> int:
        """
        Compute effective TTL with optional jitter.

        Args:
            ttl (int | None):
                Requested TTL override.

        Returns:
            int:
                Effective TTL in seconds.
        """

        effective_ttl = ttl or self.default_ttl

        if self.use_jitter:
            return get_ttl_with_jitter(effective_ttl)

        return effective_ttl

    @property
    def redis_client(self) -> Redis:
        """
        Get Redis client instance.

        Returns:
            Redis:
                Active Redis client.
        """

        if self.redis:
            return self.redis

        if self.redis_connection_pool:
            return Redis.from_pool(connection_pool=self.redis_connection_pool)

        raise CacheNotConfigured()

    def _serialize(self, value: Any) -> bytes:
        """
        Serialize value into JSON bytes.

        Uses:
        - pydantic TypeAdapter for robust serialization
        - orjson optionally for higher performance

        Args:
            value (Any):
                Value to serialize.

        Returns:
            bytes:
                Serialized JSON bytes.
        """

        if self.use_orjson:
            python_value = TypeAdapter(type(value)).dump_python(
                value,
                mode="json",
            )

            return orjson.dumps(python_value)

        return TypeAdapter(type(value)).dump_json(value)

    def _deserialize(
        self,
        data: bytes | str,
    ) -> Any:
        """
        Deserialize JSON payload.

        Args:
            data (bytes | str):
                Raw serialized payload.

        Returns:
            Any:
                Deserialized value.
        """

        if self.model:
            return TypeAdapter(self.model).validate_json(data)

        if self.use_orjson:
            return orjson.loads(data)

        if isinstance(data, bytes):
            data = data.decode()

        return json.loads(data)

    async def get(
        self,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> T | None:
        """
        Retrieve a cached value.

        Automatically deserializes JSON into the configured model type.

        Args:
            identifier (str):
                Unique cache identifier.

            params (dict[str, Any] | None):
                Optional parameters used in cache key generation.

        Returns:
            T | None:
                Cached value if found, otherwise None.
        """

        try:
            key = self._build_key(identifier, params)

            data = await self.redis_client.get(key)

            if data is None:
                return None

            return self._deserialize(data)

        except Exception as e:
            logger.warning(f"Cache: Cache get failed for " f"{identifier}: {e}")
            return None

    async def set(
        self,
        identifier: str,
        value: T,
        ttl: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """
        Store a value in cache.

        Automatically serializes:
        - primitives
        - dict/list
        - tuples
        - UUIDs
        - datetimes
        - Decimal
        - Enum
        - Pydantic models
        - nested structures

        Args:
            identifier (str):
                Unique cache identifier.

            value (T):
                Value to cache.

            ttl (int | None):
                Cache expiration time in seconds.

            params (dict[str, Any] | None):
                Optional parameters used in cache key generation.

        Returns:
            bool:
                True if successfully cached, otherwise False.
        """

        try:
            key = self._build_key(identifier, params)

            effective_ttl = self._get_ttl(ttl)

            data = self._serialize(value)

            await self.redis_client.set(
                key,
                data,
                ex=effective_ttl,
            )

            return True

        except Exception as e:
            logger.error(f"Cache: Cache set failed for " f"{identifier}: {e}")
            return False

    async def delete(
        self,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """
        Delete a cached value.

        Args:
            identifier (str):
                Unique cache identifier.

            params (dict[str, Any] | None):
                Optional parameters used in cache key generation.

        Returns:
            bool:
                True if key existed and was deleted.
        """

        try:
            key = self._build_key(identifier, params)

            result = await self.redis_client.delete(key)

            return result > 0

        except Exception as e:
            logger.error(f"Cache: Cache delete failed for " f"{identifier}: {e}")
            return False

    async def exists(
        self,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check whether a cache key exists.

        Args:
            identifier (str):
                Unique cache identifier.

            params (dict[str, Any] | None):
                Optional parameters used in cache key generation.

        Returns:
            bool:
                True if cache key exists.
        """

        try:
            key = self._build_key(identifier, params)

            return await self.redis_client.exists(key) > 0

        except Exception as e:
            logger.warning(f"Cache: Cache exists check failed " f"for {identifier}: {e}")
            return False

    async def get_or_set(
        self,
        identifier: str,
        factory: Callable[[], Awaitable[T]],
        ttl: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> T:
        """
        Retrieve cached value or compute and cache it.

        Implements the cache-aside pattern.

        Args:
            identifier (str):
                Unique cache identifier.

            factory (Callable[[], Awaitable[T]]):
                Async factory used to compute value on cache miss.

            ttl (int | None):
                Cache expiration time in seconds.

            params (dict[str, Any] | None):
                Optional parameters used in cache key generation.

        Returns:
            T:
                Cached or newly computed value.
        """

        cached = await self.get(identifier, params)

        if cached is not None:
            return cached

        value = await factory()

        if isinstance(value, Exception):
            raise value

        await self.set(identifier, value, ttl, params)

        return value

    async def invalidate_pattern(
        self,
        pattern: str = "*",
    ) -> int:
        """
        Delete all cache keys matching a pattern.

        Uses Redis SCAN internally.

        Args:
            pattern (str):
                Cache key pattern relative to the namespace.

        Returns:
            int:
                Number of deleted keys.
        """

        count = 0

        full_pattern = f"{self.prefix}:" f"{self.version}:" f"{self.namespace}:" f"{pattern}"

        try:
            async for key in self.redis_client.scan_iter(match=full_pattern):
                await self.redis_client.delete(key)
                count += 1

            if count > 0:
                logger.info(f"Cache: Invalidated {count} keys " f"matching {full_pattern}")

            return count

        except Exception as e:
            logger.error(f"Cache: Pattern invalidation failed " f"for {pattern}: {e}")

            return count

    async def get_ttl(
        self,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> int:
        """
        Get remaining TTL for a cache key.

        Redis semantics:
        - -2 => key does not exist
        - -1 => key exists without expiration

        Args:
            identifier (str):
                Unique cache identifier.

            params (dict[str, Any] | None):
                Optional parameters used in cache key generation.

        Returns:
            int:
                Remaining TTL in seconds.
        """

        try:
            key = self._build_key(identifier, params)

            return await self.redis_client.ttl(key)

        except Exception as e:
            logger.warning(f"Cache: TTL check failed " f"for {identifier}: {e}")

            return -2
