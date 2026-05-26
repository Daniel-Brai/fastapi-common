from contextlib import asynccontextmanager, contextmanager

from lib.monitoring.database.detector import DetectorConfig, N1Detector
from lib.monitoring.database.tracker import clear_request_log, start_request_log


class _TrackResult:
    def __init__(self) -> None:
        self.violations: list = []
        self.query_count: int = 0

    def assert_no_n1(self) -> None:
        if self.violations:
            msg = "N+1 violations detected:\n"
            msg += "\n".join(str(v) for v in self.violations)
            raise AssertionError(msg)


@contextmanager
def track_queries(config: DetectorConfig | None = None):
    """
    Sync context manager::

        with track_queries(DetectorConfig(threshold=2)) as result:
            db_operation()

        print(result.violations)
    """

    result = _TrackResult()
    detector = N1Detector(config or DetectorConfig())
    log = start_request_log()
    try:
        yield result
    finally:
        result.violations = detector.analyse(log)
        result.query_count = log.count
        clear_request_log()


@asynccontextmanager
async def track_queries_async(config: DetectorConfig | None = None):
    """
    Async context manager::

        async with track_queries_async() as result:
            await db_operation()

        assert result.violations == []
    """

    result = _TrackResult()
    detector = N1Detector(config or DetectorConfig())
    log = start_request_log()

    try:
        yield result
    finally:
        result.violations = detector.analyse(log)
        result.query_count = log.count
        clear_request_log()
