import hashlib
import json
import random
from typing import Any


def build_cache_key(
    namespace: str,
    identifier: str,
    params: dict[str, Any] | None = None,
    prefix: str = "cache",
    version: str = "v1",
    include_version: bool = True,
) -> str:
    """
    Generate deterministic, collision-resistant cache keys

    Format: {prefix}:{version}:{namespace}:{identifier}[:{param_hash}]

    Args:
        namespace: Cache namespace (e.g., "users", "products")
        identifier: Unique identifier within namespace
        params: Optional dict of parameters to hash into key
        prefix: Key prefix (default: "cache")
        version: Cache version for invalidation (default: "v1")
        include_version: Whether to include version in key

    Examples:

    >>> build_cache_key("users", "123")
    'cache:v1:users:123'

    >>> build_cache_key("products", "456", params={"color": "red", "size": "M"})
    'cache:v1:products:456:3a1f2e4b5c6d7e8f9a0b1c2d3e4f56'
    """

    parts = [prefix]

    if include_version:
        parts.append(version)

    parts.extend([namespace, identifier])

    if params:
        param_str = json.dumps(params, sort_keys=True)
        param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:12]
        parts.append(param_hash)

    return ":".join(parts)


def get_ttl_with_jitter(base_ttl: int, jitter_percent: float = 0.1) -> int:
    """
    Add random variance to TTL to prevent cache stampedes

    Prevents thundering herd when many keys expire simultaneously

    Args:
        base_ttl: Base TTL in seconds
        jitter_percent: Percentage of jitter (0.0-1.0)

    Examples:

    >>> get_ttl_with_jitter(300)  # 300s ± 30s (270-330)
    285
    >>> get_ttl_with_jitter(600, 0.2)  # 600s ± 120s (480-720)
    540
    """
    jitter = int(base_ttl * jitter_percent)
    return base_ttl + random.randint(-jitter, jitter)  # noqa: S311


def invalidate_pattern(
    namespace: str,
    pattern: str = "*",
    prefix: str = "cache",
    version: str = "v1",
) -> str:
    """
    Build pattern for bulk invalidation using SCAN

    Args:
        namespace: Cache namespace
        pattern: Pattern to match (default: "*" for all)
        prefix: Key prefix (default: "cache")
        version: Cache version (default: "v1")

    Examples:

    >>> invalidate_pattern("users")
    'cache:v1:users:*'
    >>> invalidate_pattern("products", pattern="123:*")
    'cache:v1:products:123:*'
    """

    return f"{prefix}:{version}:{namespace}:{pattern}"
