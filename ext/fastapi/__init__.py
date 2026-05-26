"""
Extensions for FastAPI

This module provides a set of extensions for FastAPI, including controllers,request and response utilities, and middlewares, and services.
"""

from .controllers import (
    Controller,
    before_action,
    configure_controllers,
    delete,
    get,
    head,
    options,
    patch,
    post,
    put,
    trace,
)
from .middlewares import CorrelationIdMiddleware, ETagMiddleware, RequestTimingMiddleware, SecurityHeadersMiddleware
from .requests import check_if_path_excluded, get_client_ip, get_request_id, get_user_agent
from .responses import (
    IBaseResponse,
    IResponse,
    JSONResponse,
    ORJSONResponse,
    build_json_response,
    build_orjson_response,
)
from .services import BaseService, IORunnableService, Service, ServiceError, StandaloneRunnableService

__all__ = [
    "configure_controllers",
    "Service",
    "BaseService",
    "IORunnableService",
    "StandaloneRunnableService",
    "check_if_path_excluded",
    "get_client_ip",
    "get_request_id",
    "get_user_agent",
    "IBaseResponse",
    "IResponse",
    "build_json_response",
    "build_orjson_response",
    "JSONResponse",
    "ORJSONResponse",
    "Controller",
    "put",
    "get",
    "post",
    "delete",
    "patch",
    "trace",
    "head",
    "options",
    "before_action",
    "ETagMiddleware",
    "SecurityHeadersMiddleware",
    "CorrelationIdMiddleware",
    "RequestTimingMiddleware",
    "ServiceError",
]
