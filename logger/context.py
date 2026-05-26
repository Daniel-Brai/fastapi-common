from typing import Any

from structlog.contextvars import bind_contextvars, clear_contextvars


def bind_log_context(**kwargs: Any) -> None:
    bind_contextvars(**kwargs)


def clear_log_context() -> None:
    clear_contextvars()
