from typing import Callable

from fastapi import Request, status
from fastapi_problem.cors import CorsConfiguration
from fastapi_problem.error import Problem
from fastapi_problem.handler import ExceptionHandler, new_exception_handler
from rfc9457 import error_class_to_type

from lib.exceptions.constants import get_default_exception_registry
from lib.exceptions.types import ExceptionRegistry
from lib.logger import get_logger

logger = get_logger("lib.exceptions.utils")


def create_problem(
    title: str | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    detail_message: str | None = None,
    transform_on_callable: str | None = None,
) -> Callable[..., Problem]:
    """
    Factory function to create standard problem handlers.

    Args:
        title (str): Title to use in the problem response.
        status_code (int): HTTP status code to return in the problem response.
        detail_message (str | None): Optional detail message
        transform_on_callable (str | None): Optional name of a callable attribute on the exception to transform it before creating the problem.

    Returns:
        A callable problem handler function.
    """

    def handler(_eh, request: Request, exc: Exception) -> Problem:
        logger.exception(
            f"{exc.__class__.__name__} exception caught",
        )

        if transform_on_callable is not None:
            attr = getattr(exc, transform_on_callable)

            if attr and callable(attr):
                exc = attr()  # type: ignore

        title_message = getattr(exc, "title", None) or title or "Error"
        detail = detail_message or getattr(exc, "message", None) or str(exc)
        status = getattr(exc, "status_code", None) or status_code
        error_type = getattr(exc, "type", None) or error_class_to_type(exc)
        headers = getattr(exc, "headers", None) or {}

        if status >= 500:
            error_type = "internal_server_error"
            detail = "An unexpected error occurred. Please try again later."

        return Problem(
            title=title_message,
            type_=error_type,
            status=status,
            detail=detail,
            instance=str(request.url.path),
            headers=headers,
        )

    return handler


def create_exception_handler(
    cors: CorsConfiguration,
    exception_registry: ExceptionRegistry,
) -> ExceptionHandler:
    """
    Create a new exception handler with the provided CORS configuration and exception registry.

    Note:
    The created exception handler will include both the provided exception registry and
    the default exception registry returned by :func:`get_default_exception_registry`.

    Args:
        cors (CorsConfiguration): The CORS configuration to apply to the exception handler.
        exception_registry (ExceptionRegistry): A registry of custom exceptions to be handled.

    Returns:
        ExceptionHandler: An instance of the ExceptionHandler with the specified configuration and registry.
    """

    eh = new_exception_handler(
        cors=cors,
        handlers=exception_registry,
    )

    eh.handlers.update(get_default_exception_registry())

    return eh
