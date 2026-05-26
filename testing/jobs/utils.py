from contextlib import contextmanager
from typing import Any, Generator, Type
from unittest.mock import patch

from .types import DispatchedJob, MockJobHandle


def make_now_capture(job_class: Type[Any], sink: list[DispatchedJob]):
    """
    Replacement for `perform_now`.

    It records the dispatch and returns a MockJobHandle.

    We are asserting that the dispatch happened, not testing the job's logic here.

    **Note**: It does NOT call `_execute` or `perform`

    """

    def capturing(*args: Any, **kwargs: Any) -> MockJobHandle:
        record = DispatchedJob(job_class=job_class, args=list(args), kwargs=kwargs, mode="now")
        sink.append(record)
        return record.handle

    return classmethod(lambda cls, *a, **kw: capturing(*a, **kw))


def make_later_capture(job_class: Type[Any], sink: list[DispatchedJob], mode: str = "later"):
    """
    Replacement for `perform_later` (and JobProxy.perform_later).

    It returns `MockJobHandle` so `.with_session()` chaining works.
    """

    def capturing(*args: Any, **kwargs: Any) -> MockJobHandle:
        record = DispatchedJob(job_class=job_class, args=list(args), kwargs=kwargs, mode=mode)
        sink.append(record)
        return record.handle

    return classmethod(lambda cls, *a, **kw: capturing(*a, **kw))


@contextmanager
def capture_jobs(*job_classes: Type[Any]) -> Generator[list[DispatchedJob], None, None]:
    """
    Intercept `perform_now` and `perform_later` on the given job classes, recording every dispatch into a local list without executing anything.

    Each call creates its own isolated sink

    Example
    -------
        ```python
        with capture_jobs(FetchFeedJob, SendEmailJob) as dispatched:
            await service.subscribe_to_feeds(user_id=1, data=body)

        assert len(dispatched) == 1
        assert dispatched[0].job_class is FetchFeedJob
        assert dispatched[0].kwargs["feed_id"] == feed.id
        assert dispatched[0].mode == "later"
        ```

    **Note**: `perform_now` dispatches also return a `MockJobHandle` (not a job
    instance) because in tests you should use `make_job()` and `job.perform()` when you want to exercise the actual job logic.
    """

    sink: list[DispatchedJob] = []

    patches = []
    for cls in job_classes:
        patches.extend(
            [
                patch.object(cls, "perform_now", new=make_now_capture(cls, sink)),
                patch.object(cls, "perform_later", new=make_later_capture(cls, sink, "later")),
            ]
        )

    for p in patches:
        p.start()

    try:
        yield sink
    finally:
        for p in patches:
            p.stop()
