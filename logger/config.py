import logging
import logging.config
from typing import Literal

import structlog
from structlog.contextvars import merge_contextvars

from lib.logger.filters import filter_sensitive_data
from lib.logger.processors import add_correlation, add_process_metadata, drop_healthcheck_logs


def configure_logging(
    config: dict | None = None,
    *,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "FATAL", "WARN"] = "INFO",
) -> None:

    DEFAULT_LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structlog": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": [
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
                    add_process_metadata,
                    add_correlation,
                    merge_contextvars,
                    filter_sensitive_data,
                    structlog.processors.dict_tracebacks,
                    structlog.processors.EventRenamer("msg"),
                ],
            }
        },
        "handlers": {
            "console": {
                "formatter": "structlog",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "level": log_level,
            }
        },
        "root": {"handlers": ["console"], "level": log_level},
        "loggers": {
            "gunicorn.access": {
                "propagate": False,
                "handlers": ["console"],
                "level": "WARNING",
            },
            "uvicorn.access": {
                "propagate": False,
                "handlers": ["console"],
                "level": "WARNING",
            },
            "httpx": {
                "propagate": False,
                "handlers": ["console"],
                "level": log_level,
            },
        },
    }

    if config is None:
        logging.getLogger("uvicorn.error").handlers = [logging.NullHandler()]
        logging.getLogger("gunicorn.error").handlers = [logging.NullHandler()]
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

    logging.config.dictConfig(config or DEFAULT_LOG_CONFIG)

    LOG_LEVEL_VALUE = logging.getLevelNamesMapping().get(log_level)

    assert LOG_LEVEL_VALUE is not None, f"Invalid log level: {log_level}"

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL_VALUE),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_correlation,
            merge_contextvars,
            drop_healthcheck_logs,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
            add_process_metadata,
            filter_sensitive_data,
            structlog.processors.dict_tracebacks,
            structlog.processors.EventRenamer("msg"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
    )
