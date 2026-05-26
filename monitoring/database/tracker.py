from contextvars import ContextVar

from lib.monitoring.database.schemas import QueryLog

# one QueryLog per request so that is isolated across tasks or threads
_current_log: ContextVar[QueryLog | None] = ContextVar("_current_log", default=None)


def start_request_log() -> QueryLog:
    log = QueryLog()
    _current_log.set(log)
    return log


def get_request_log() -> QueryLog | None:
    return _current_log.get()


def clear_request_log() -> None:
    _current_log.set(None)
