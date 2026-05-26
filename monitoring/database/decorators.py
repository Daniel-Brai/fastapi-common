import functools
import inspect
from typing import Any, Callable

from lib.monitoring.database.context import track_queries, track_queries_async
from lib.monitoring.database.detector import DetectorConfig


def monitor_queries(
    threshold: int = 3,
    allowlist_patterns: list[str] | None = None,
    raise_on_violation: bool = True,
) -> Callable:
    """
    Decorator that asserts no N+1 queries occur inside the function.

    Works on both sync and async functions::

        @monitor_queries(threshold=2)
        async def test_list_users(session):
            await fetch_all_users(session)
    """

    cfg = DetectorConfig(
        threshold=threshold,
        allowlist_patterns=allowlist_patterns or [],
        on_violation=None,
    )

    def decorator(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with track_queries_async(cfg) as result:
                    ret = await fn(*args, **kwargs)

                if raise_on_violation:
                    result.assert_no_n1()

                return ret

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with track_queries(cfg) as result:
                    ret = fn(*args, **kwargs)

                if raise_on_violation:
                    result.assert_no_n1()
                return ret

            return sync_wrapper

    return decorator
