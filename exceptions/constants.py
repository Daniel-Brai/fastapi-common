from fastapi import HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi_problem.handler import http_exception_handler_, request_validation_handler_

from lib.exceptions.types import ExceptionRegistry


def get_default_exception_registry() -> ExceptionRegistry:
    from lib.exceptions.utils import create_problem

    return {
        ValueError: create_problem(title="Invalid Request"),
        RequestValidationError: request_validation_handler_,
        HTTPException: http_exception_handler_,
        Exception: create_problem(
            title="Internal Server Error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
    }
