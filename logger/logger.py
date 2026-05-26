import structlog


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)
