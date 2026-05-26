from fastapi import status


class ThrottlerError(Exception):
    """Base exception for the throttler library."""


class ThrottlerNotConfiguredError(RuntimeError):
    """Raised when throttler is not configured properly."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "Throttler is not configured. Call configure_throttler() at application startup.")


class RateLimitExceededError(ThrottlerError):
    """
    Raised when a client exceeds their rate limit.

    Attributes
    ----------
    retry_after
        Seconds until the rate limit window resets.
    limit
        Total allowed requests in the window.
    remaining
        Remaining requests in the current window (always 0 here).
    reset_at
        Unix timestamp when the window resets.
    headers
        Ready-to-use HTTP headers dict for the 429 response.
    """

    def __init__(
        self,
        retry_after: int,
        limit: int = 0,
        remaining: int = 0,
        reset_at: float = 0.0,
        headers: dict | None = None,
    ) -> None:
        self.type = "rate_limit_exceeded"
        self.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.headers = headers or {
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(reset_at)),
        }
        super().__init__("Rate limit exceeded.")
