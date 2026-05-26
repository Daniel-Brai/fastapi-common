import logging
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "authorization",
    "auth",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "api-token",
    "api_token",
    "access_token",
    "refresh_token",
    "token",
    "session",
    "session_id",
    "cookie",
    "cookies",
    "credit_card",
    "creditcard",
    "card_number",
    "ssn",
}

SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "encryption",
    "secret",
    "token",
    "salt",
    "hash",
    "credential",
    "cookie",
    "session",
)

REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in SENSITIVE_KEYS:
        return True
    return any(substring in lowered for substring in SENSITIVE_KEY_SUBSTRINGS)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_value(val) if key.lower() not in SENSITIVE_KEYS else REDACTED for key, val in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return type(value)(_redact_value(item) for item in value)
    return value


def filter_sensitive_data(_: Any, __: str, event_dict: structlog.types.EventDict) -> structlog.types.EventDict:
    for key, value in list(event_dict.items()):
        if _is_sensitive_key(key):
            event_dict[key] = REDACTED
        elif isinstance(value, dict):
            event_dict[key] = _redact_value(value)
        elif isinstance(value, (list, tuple, set)):
            event_dict[key] = _redact_value(value)
    return event_dict


class SensitiveFilter(logging.Filter):
    """Logging filter to keep sensitive values out of structured logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "args") and isinstance(record.args, dict):
            record.args = _redact_value(record.args)
        return True
