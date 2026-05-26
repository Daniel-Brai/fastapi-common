from typing import Any

import sentry_sdk


def configure_sentry(dsn: str, environment: str | Any, **kwargs: Any) -> None:
    """
    Initialize Sentry for error tracking and performance monitoring.

    Args:
        dsn (str): The Data Source Name for Sentry, which specifies the project and authentication details.
        environment (str | Any): The environment in which the application is running (e.g., "production", "staging", "development").
        **kwargs (Any): Additional keyword arguments to pass to the Sentry SDK initialization. use :class:`sentry_sdk.consts.ClientConstructor`.
    """

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        enable_tracing=True,
        send_default_pii=False,
        **kwargs,
    )
