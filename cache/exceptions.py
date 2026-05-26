class CacheError(Exception):
    """
    Base exception for cache-related errors.
    """

    pass


class CacheNotConfigured(RuntimeError):
    """
    Raised when the cache is not configured but an operation is attempted.
    """

    pass
