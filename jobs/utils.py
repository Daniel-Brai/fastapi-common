from datetime import date, datetime, time
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel

if TYPE_CHECKING:
    from lib.jobs.base import BaseJob


def fqn(cls: "type[BaseJob]") -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def normalize_job_arg(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return normalize_job_arg(value.model_dump(mode="json", exclude_none=False))

    if isinstance(value, dict):
        return {k: normalize_job_arg(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        normalized = [normalize_job_arg(v) for v in value]
        return tuple(normalized) if isinstance(value, tuple) else normalized

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    return value
