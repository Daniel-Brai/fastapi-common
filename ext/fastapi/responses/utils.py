from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import orjson
from fastapi import status
from pydantic import BaseModel
from starlette.responses import JSONResponse

from .schemas import IBaseResponse, IResponse


def _default_serializer(obj: Any) -> Any:
    """
    Default serializer for orjson to handle non-standard types
    """

    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="python")

    if isinstance(obj, UUID):
        return str(obj)

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, Decimal):
        return float(obj)

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, int):
        if obj > 9223372036854775807 or obj < -9223372036854775808:
            return str(obj)

    return str(obj)


class ORJSONResponse(JSONResponse):
    """
    Custom `ORJSONResponse` that uses `orjson` for serialization, with support for additional types like Pydantic models, UUIDs, datetimes, Enums, Decimals, and Paths.
    """

    def render(self, content: Any) -> bytes:
        return orjson.dumps(
            content,
            default=_default_serializer,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
        )


def build_orjson_response(
    message: str,
    data: Any | None = None,
    metadata: Any | None = None,
    *,
    base: bool = False,
    status_code: int = status.HTTP_200_OK,
    headers: dict[str, Any] | None = None,
) -> ORJSONResponse:
    """
    Creates a standardized API JSON response.

    Args:
        data (Any): The main data payload of the response.
        message (str | None): An optional message providing additional information about the response.
        metadata (Any | None): Optional metadata about the response

    Returns:
        IResponse[Any, Any]: An instance of `IResponse` containing the provided data, message, and metadata.
    """

    if base:
        response = IBaseResponse(
            message=message,
        )
    else:
        response = IResponse(
            message=message,
            data=data,
            metadata=metadata,
        )

    return ORJSONResponse(content=response.model_dump(mode="python"), status_code=status_code, headers=headers)


def build_json_response(
    message: str,
    data: Any | None = None,
    metadata: Any | None = None,
    *,
    base: bool = False,
    status_code: int = status.HTTP_200_OK,
    headers: dict[str, Any] | None = None,
) -> JSONResponse:
    """
    Creates a standardized API JSON response using FastAPI's default JSONResponse.

    Args:
        data (Any): The main data payload of the response.
        message (str | None): An optional message providing additional information about the response.
        metadata (Any | None): Optional metadata about the response

    Returns:
        IResponse[Any, Any]: An instance of `IResponse` containing the provided data, message, and metadata.
    """

    if base:
        response = IBaseResponse(
            message=message,
        )
    else:
        response = IResponse(
            message=message,
            data=data,
            metadata=metadata,
        )

    return JSONResponse(
        content=response.model_dump(mode="python", serialize_as_any=True, fallback=_default_serializer),
        status_code=status_code,
        headers=headers,
    )
