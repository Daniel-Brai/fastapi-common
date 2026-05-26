import unittest
from typing import Any, List, Type

from .types import DispatchedJob
from .utils import capture_jobs


class TestJobCase(unittest.IsolatedAsyncioTestCase):
    """
    unittest-flavoured base for job tests.
    """

    job_class: Type[Any] | None = None

    async def asyncSetUp(self) -> None:
        if self.job_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `job_class`.")

        from lib.testing.database import MockAsyncSession

        self.db = MockAsyncSession()

    async def asyncTearDown(self) -> None:
        self.db.reset()

    def make_job(self) -> Any:
        """
        Create a real instance of :attr:`job_class` with hooks intact.

        Inject dependencies directly onto the returned instance:

            job = self.make_job()
            job.feed_repo = AsyncMock(...)
            await job.perform(feed_id=feed.id, user_id=1)
        """

        return self.job_class()  # type: ignore

    def capture_jobs(self, *job_classes: Type[Any]):
        """
        A helper to call the capture_jobs context manager from tests without importing it directly.
        """

        return capture_jobs(*job_classes)

    def assert_job_dispatched(
        self,
        dispatched: list[DispatchedJob],
        job_class: Type[Any],
        mode: str = "later",
        count: int = 1,
    ) -> None:
        """
        Assert that *job_class* was dispatched *count* times with *mode*.
        """

        matching = [d for d in dispatched if d.job_class is job_class and d.mode == mode]
        self.assertEqual(
            len(matching),
            count,
            f"Expected {count} dispatch(es) of {job_class.__name__} "
            f"(mode={mode!r}), found {len(matching)}.\n"
            f"All dispatched: {dispatched}",
        )

    def patch(self, import_path: str) -> Any:
        """
        Patch a service class at its import path.

        Usage:

            with self.patch("services.feed_fetcher.FeedFetcherService") as MockSvc:
                MockSvc.return_value.run = AsyncMock()
                self.make_job().perform(...)
        """

        from unittest import mock

        return mock.patch(import_path)

    def assert_no_jobs_dispatched(self, dispatched: List[DispatchedJob]) -> None:
        self.assertEqual(
            len(dispatched),
            0,
            f"Expected no jobs dispatched, got: {dispatched}",
        )

    def assert_job_kwargs(
        self,
        dispatched: List[DispatchedJob],
        job_class: Type[Any],
        **expected_kwargs: Any,
    ) -> None:
        """
        Assert that the first dispatch of *job_class* was called with at least the given kwargs (subset match).
        """

        matching = [d for d in dispatched if d.job_class is job_class]
        self.assertTrue(
            matching,
            f"No dispatch found for {job_class.__name__}",
        )

        actual = matching[0].kwargs
        for key, expected in expected_kwargs.items():
            self.assertIn(key, actual, f"kwarg {key!r} not in dispatch kwargs")
            self.assertEqual(
                actual[key],
                expected,
                f"kwarg {key!r}: expected {expected!r}, got {actual[key]!r}",
            )
