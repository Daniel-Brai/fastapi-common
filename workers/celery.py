from celery import Celery


def create_celery_app(
    broker_url: str,
    result_backend: str,
    results_expires: int = 4 * 60 * 60,
    default_queue: str = "default",
    job_modules: list[str] | None = None,
    **celery_config_kwargs
) -> Celery:
    """
    Creates and configure the Celery app for background job processing.

    Initializes a Celery application with the specified broker and result backend, along with sensible defaults for task acknowledgment, queue management, and timezone.

    Additional Celery configuration options can be provided via keyword arguments.

    Parameters
    ----------
    broker_url: str
        The URL of the message broker (e.g., Redis, RabbitMQ) to use for task queuing.
    result_backend: str
        The URL of the result backend (e.g., Redis, database) to store task results.
    results_expires: int
        Time in seconds after which stored task results will expire. Defaults to 4 hours.
    default_queue: str
        The name of the default queue to which tasks will be sent if no other queue is specified. Defaults to "default".
    job_modules: list[str] | None
        A list of module paths (e.g., ["app.jobs"]) to include for task discovery. If None, no modules will be included.
    **celery_config_kwargs
        Additional keyword arguments to update the Celery configuration. These can be used to override any default settings or add custom configurations as needed.

    Returns
    -------
    Celery
        The configured Celery application instance.
    """

    celery_app = Celery(__name__, include=job_modules)

    DEFAULT_CELERY_CONFIG = {
        "broker_url": broker_url,
        "result_backend": result_backend,
        "result_expires": results_expires,
        "task_acks_late": True,
        "task_default_queue": default_queue,
        "task_create_missing_queues": True,
        "broker_connection_retry_on_startup": True,
        "timezone": "UTC",
    }

    celery_app.conf.update(DEFAULT_CELERY_CONFIG)

    if celery_config_kwargs:
        celery_app.conf.update(celery_config_kwargs)

    return celery_app
