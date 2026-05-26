from typing import TYPE_CHECKING, Any, Callable

from lib.jobs.registry import JobRegistry, job_registry

if TYPE_CHECKING:
    from lib.jobs.adapters import AbstractAdapter
    from lib.jobs.base import BaseJob


def configure_jobs(
    adapter: AbstractAdapter,
    *,
    modules: list[str] | None = None,
    before_perform: list[Callable[["BaseJob"], Any]] | None = None,
    after_perform: list[Callable[["BaseJob"], Any]] | None = None,
    on_success: list[Callable[["BaseJob"], Any]] | None = None,
    on_error: list[Callable[["BaseJob", Exception], Any]] | None = None,
) -> JobRegistry:
    """
    Configure the job adapter.

    Call this at startup

    Pass `modules` to auto-import the modules where your job classes live so they
    are registered before the adapter starts.

    You can also provide global lifecycle callbacks for every job:
    `before_perform`, `after_perform`, `on_success`, and `on_error`.

    Examples:

        configure_jobs(
            DBAdapter(engine, workers=4, poll_interval=2.0),
            modules=["myapp.jobs.email", "myapp.jobs.reports"],
        )
    """

    if modules is not None:
        unique_modules = set(modules)
    else:
        unique_modules = set()

    return job_registry.configure_jobs(
        adapter,
        modules=list(unique_modules),
        before_perform=before_perform,
        after_perform=after_perform,
        on_success=on_success,
        on_error=on_error,
    )


def get_registry() -> JobRegistry:
    """
    Get the global job registry.

    Raises:
        JobConfigurationError: If no adapter has been configured yet. Call `configure_jobs()` at startup.
    """

    job_registry.assert_configured()

    return job_registry


def get_adapter() -> AbstractAdapter:
    """
    Get the configured job adapter.

    Raises:
        JobConfigurationError: If no adapter has been configured yet. Call `configure_jobs()` at startup.
    """

    job_registry.assert_configured()

    return job_registry.get_adapter()


def get_adapter_name() -> str:
    """
    Get the type of the configured adapter, e.g "db", "celery", etc.

    Raises:
        JobConfigurationError: If no adapter has been configured yet. Call `configure_jobs()` at
    """

    job_registry.assert_configured()

    return job_registry.get_adapter_name()


def get_job_queues() -> list[str]:
    """
    Get a list of all unique queue names from registered jobs.

    Raises:
        JobConfigurationError: If no adapter has been configured yet. Call `configure_jobs()` at
    """

    job_registry.assert_configured()

    unique_queues = {job_cls.queue for job_cls in job_registry.jobs.values()}

    return list(unique_queues)
