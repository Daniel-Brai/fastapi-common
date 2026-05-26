import importlib
from typing import TYPE_CHECKING, Any, Callable, Type

from lib.jobs.exceptions import JobConfigurationError, JobNotFoundError
from lib.jobs.utils import fqn
from lib.logger import get_logger

if TYPE_CHECKING:
    from lib.jobs.adapters import AbstractAdapter
    from lib.jobs.base import BaseJob


logger = get_logger("jobs.registry")


class JobRegistry:
    def __init__(self):
        self._adapter: AbstractAdapter | None = None
        self._jobs: dict[str, Type[BaseJob]] = {}
        self._before_perform_callbacks: list[Callable[["BaseJob"], Any]] = []
        self._after_perform_callbacks: list[Callable[["BaseJob"], Any]] = []
        self._on_success_callbacks: list[Callable[["BaseJob"], Any]] = []
        self._on_error_callbacks: list[Callable[["BaseJob", Exception], Any]] = []

    @property
    def jobs(self) -> "dict[str, Type[BaseJob]]":
        return self._jobs

    def assert_configured(self):
        if self._adapter is None:
            raise JobConfigurationError("No job adapter configured. Call jobs.configure() at startup.")

    def configure_jobs(
        self,
        adapter: "AbstractAdapter",
        *,
        modules: list[str] | None = None,
        before_perform: list[Callable[["BaseJob"], Any]] | None = None,
        after_perform: list[Callable[["BaseJob"], Any]] | None = None,
        on_success: list[Callable[["BaseJob"], Any]] | None = None,
        on_error: list[Callable[["BaseJob", Exception], Any]] | None = None,
    ) -> "JobRegistry":
        """
        Automatically import the specified modules to ensure all job classes are registered, then set the adapter.
        """
        if modules:
            for mod in modules:
                importlib.import_module(mod)

        self._adapter = adapter
        self._before_perform_callbacks = list(before_perform) if before_perform else []
        self._after_perform_callbacks = list(after_perform) if after_perform else []
        self._on_success_callbacks = list(on_success) if on_success else []
        self._on_error_callbacks = list(on_error) if on_error else []

        logger.info(
            "Jobs configured with adapter %s and modules %s",
            type(adapter).__name__,
            modules or [],
        )

        return self

    def get_adapter(self) -> "AbstractAdapter":
        if self._adapter is None:
            raise JobConfigurationError("No job adapter configured. Call jobs.configure() at startup.")

        return self._adapter

    def get_adapter_name(self) -> str:
        return self.get_adapter().name()

    @property
    def before_perform_callbacks(self) -> list[Callable[["BaseJob"], Any]]:
        return self._before_perform_callbacks

    @property
    def after_perform_callbacks(self) -> list[Callable[["BaseJob"], Any]]:
        return self._after_perform_callbacks

    @property
    def on_success_callbacks(self) -> list[Callable[["BaseJob"], Any]]:
        return self._on_success_callbacks

    @property
    def on_error_callbacks(self) -> list[Callable[["BaseJob", Exception], Any]]:
        return self._on_error_callbacks

    def register(self, cls: Any) -> "Type[BaseJob]":
        """
        Mark a class as a job by registering it in the registry.
        """
        from lib.jobs.base import BaseJob

        job_fqn = fqn(cls)
        if job_fqn in self._jobs:
            return self._jobs[job_fqn]

        if not issubclass(cls, BaseJob):
            raise JobConfigurationError(f"Cannot register {cls!r} as a job. It must inherit from BaseJob.")

        self._jobs[job_fqn] = cls

        return cls

    def resolve(self, name: str) -> "Type[BaseJob]":
        if name not in self._jobs:
            raise JobNotFoundError(
                f"Job class {name!r} is not registered. "
                "Ensure the module that defines it is imported before the worker starts."
            )
        return self._jobs[name]


job_registry = JobRegistry()
