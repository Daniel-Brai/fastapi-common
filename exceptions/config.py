from fastapi import FastAPI
from fastapi_problem.handler import ExceptionHandler, add_exception_handler

from lib.logger import get_logger

logger = get_logger("lib.exceptions.config")


def configure_exception_handler(
    app: FastAPI,
    eh: ExceptionHandler,
    *,
    strict_rfc9457: bool = False,
) -> ExceptionHandler:
    """
    Configure the exception handler for the application.

    This function adds the provided exception handler to the FastAPI application, allowing it to handle exceptions and
    return appropriate responses to the client.

    Args:
        app (FastAPI): The FastAPI application instance.
        eh (ExceptionHandler): The exception handler instance to be added to the application.
        strict_rfc9457 (bool): If True, the exception handler will strictly adhere to RFC 9457 when generating problem responses. Defaults to False.

    Returns:
        ExceptionHandler: The configured exception handler instance.

    Example:

        ```python
        configure_exception_handler(
            app,
            create_exception_handler(
                cors=CorsConfiguration(
                    allow_origins=["*"],
                    allow_methods=["*"],
                    allow_headers=["*"],
                    allow_credentials=True,
                ),
                exception_registry={
                    CustomException: create_problem(title="Custom Exception", status_code=status.HTTP_400_BAD_REQUEST),
                }
            ),
        )
        ```
    """

    ret = add_exception_handler(app, eh, strict_rfc9457=strict_rfc9457)
    logger.info("Exception handler configured successfully.")

    return ret
