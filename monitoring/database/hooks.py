import time

from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import AsyncEngine

from lib.monitoring.database.helpers import capture_stack, normalize_sql
from lib.monitoring.database.schemas import CapturedQuery
from lib.monitoring.database.tracker import get_request_log


def instrument_monitoring(engine: Engine | AsyncEngine) -> None:
    """
    Attach N+1 tracking listeners to *engine*.

    Pass either a sync ``Engine`` or an ``AsyncEngine``; we unwrap
    the async wrapper automatically.

        engine = create_engine(DATABASE_URL)
        instrument_monitoring(engine)

        # or async:
        async_engine = create_async_engine(DATABASE_URL)
        instrument_monitoring(async_engine)
    """

    sync_engine: Engine = engine.sync_engine if isinstance(engine, AsyncEngine) else engine  # type: ignore[union-attr]
    _attach_listeners(sync_engine)


def remove_instrumentation(engine: Engine | AsyncEngine) -> None:
    """
    Remove listeners attached by `instrument_monitoring`

    It can be useful in tests.
    """

    sync_engine: Engine = engine.sync_engine if isinstance(engine, AsyncEngine) else engine  # type: ignore[union-attr]
    _detach_listeners(sync_engine)


def _attach_listeners(engine: Engine) -> None:
    event.listen(engine, "before_cursor_execute", _before_execute, retval=False)
    event.listen(engine, "after_cursor_execute", _after_execute, retval=False)


def _detach_listeners(engine: Engine) -> None:
    if event.contains(engine, "before_cursor_execute", _before_execute):
        event.remove(engine, "before_cursor_execute", _before_execute)
    if event.contains(engine, "after_cursor_execute", _after_execute):
        event.remove(engine, "after_cursor_execute", _after_execute)


_START_KEY = "_monitor_db_query_start"


def _before_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001, ANN001
    conn.info[_START_KEY] = time.perf_counter()


def _after_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001, ANN001
    log = get_request_log()
    if log is None:
        return

    start: float = conn.info.pop(_START_KEY, time.perf_counter())
    duration_ms = (time.perf_counter() - start) * 1000

    log.record(
        CapturedQuery(
            raw_sql=statement,
            normalized_sql=normalize_sql(statement),
            params=parameters,
            duration_ms=duration_ms,
            stack=capture_stack(),
        )
    )
