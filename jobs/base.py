import asyncio
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, ClassVar, Coroutine, Type

from lib.jobs.config import get_adapter
from lib.jobs.handle import JobHandle
from lib.jobs.meta import JobMeta
from lib.jobs.registry import job_registry
from lib.jobs.schemas import Shim
from lib.jobs.types import JobSchedule
from lib.jobs.utils import normalize_job_arg
from lib.logger import get_logger


class BaseJob(metaclass=JobMeta):
    """
    Base class for all application jobs.

    Examples:

        ##### One-off usage

        class SendEmailJob(BaseJob):
            queue            = "mailers"
            max_attempts     = 5
            discard_on_success = True   # default
            retry_on         = (MailerConnectionError,)

            def perform(self, user_id: int, template: str) -> None:
                ...

        SendEmailJob.perform_later(user_id=42, template="welcome")
        SendEmailJob.perform_now(user_id=42, template="welcome")
        SendEmailJob.set(wait=timedelta(minutes=5)).perform_later(user_id=42, template="welcome")

        ##### Recurring usage

        class DailyReportJob(BaseJob):
            queue              = "reports"
            discard_on_success = False   # keep for audit
            schedule           = cron("0 9 * * *")

            def perform(self) -> None:
                ...
    """

    queue: ClassVar[str] = "default"
    priority: ClassVar[int] = 0
    max_attempts: ClassVar[int] = 3
    discard_on_success: ClassVar[bool] = True
    schedule: ClassVar[JobSchedule | None] = None
    retry_on: ClassVar[tuple[type[Exception], ...]] = (Exception,)

    before_perform_callbacks: ClassVar[list[Callable[["BaseJob"], Any]]] = []
    after_perform_callbacks: ClassVar[list[Callable[["BaseJob"], Any]]] = []
    on_success_callbacks: ClassVar[list[Callable[["BaseJob"], Any]]] = []
    on_error_callbacks: ClassVar[list[Callable[["BaseJob", Exception], Any]]] = []

    # List of Shim instances applied in order before perform() is called.
    # Each shim fires only when its `when` predicate returns True, allowing
    # multiple independent transforms to coexist without conflicts.
    #
    # Example:
    #   class SendEmailJob(BaseJob):
    #       migrations = [
    #           # Moving from v1 to v2: positional (user_id, template) → kwargs
    #           Shim(
    #               when  = lambda a, kw: len(a) >= 2 and not kw,
    #               apply = lambda a, kw: ([], {"user_id": a[0], "template": a[1]}),
    #           ),
    #           # Moving v2 to v3: backfill new `locale` field
    #           Shim(
    #               when  = lambda a, kw: "locale" not in kw,
    #               apply = lambda a, kw: (a, {**kw, "locale": "en"}),
    #           ),
    #       ]
    migrations: ClassVar[list["Shim"]] = []

    def __init__(self) -> None:
        self.logger = get_logger(
            f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        )

    @classmethod
    def perform_now(cls, *args: Any, **kwargs: Any) -> Any:
        """
        Execute synchronously in the calling thread
        """
        migrated_args, migrated_kwargs = cls.migrate(list(args), kwargs)
        return cls().execute(*migrated_args, **migrated_kwargs)

    @classmethod
    def perform_later(cls, *args: Any, **kwargs: Any) -> JobHandle:
        """
        Enqueue for background execution
        """
        nargs = [normalize_job_arg(a) for a in args]
        nkwargs = {k: normalize_job_arg(v) for k, v in kwargs.items()}
        record = get_adapter().enqueue(cls, args=nargs, kwargs=nkwargs)
        return JobHandle(record)

    @classmethod
    def set(
        cls, *, wait: timedelta | None = None, wait_until: datetime | None = None
    ) -> "JobProxy":
        """
        Return a proxy carrying scheduling option
        """
        return JobProxy(cls, wait=wait, wait_until=wait_until)

    def perform(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} must implement perform()")

    @classmethod
    def migrate(
        cls, args: list[Any], kwargs: dict[str, Any]
    ) -> tuple[list[Any], dict[str, Any]]:
        """
        Apply all registered migration shims in order.
        Called by the worker before perform() — never call directly.

        Each shim's `when` predicate is checked; if True, `apply` transforms
        the (args, kwargs). The output of one shim is the input of the next.
        """
        nargs = [normalize_job_arg(a) for a in args]
        nkwargs = {k: normalize_job_arg(v) for k, v in kwargs.items()}

        if len(cls.migrations) == 0:
            return nargs, nkwargs

        for shim in cls.migrations:
            if shim.when(nargs, nkwargs):
                nargs, nkwargs = shim.apply(nargs, nkwargs)

        return nargs, nkwargs

    def run_async(self, coro: Coroutine[Any, Any, Any]):
        if not asyncio.iscoroutine(coro):
            raise TypeError("`run_async` expects an awaitable coroutine")

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        else:
            return self._run_async_in_thread(coro)

    def _run_async_in_thread(self, coro: Coroutine[Any, Any, Any]) -> Any:
        result: list[Any] = []
        exc: list[BaseException] = []

        def _target() -> None:
            try:
                result.append(asyncio.run(coro))
            except BaseException as error:
                exc.append(error)

        thread = threading.Thread(target=_target)
        thread.start()
        thread.join()

        if exc:
            raise exc[0]

        return result[0] if result else None

    def _run_hooks(self, callbacks: list[Callable[..., Any]], *args: Any) -> None:
        for callback in callbacks:
            try:
                callback(self, *args)
            except Exception as exc:
                self.logger.exception(
                    "Job hook failed during %s: %s",
                    (
                        callback.__name__
                        if hasattr(callback, "__name__")
                        else type(callback).__name__
                    ),
                    exc,
                )

    def _run_before_perform_hooks(self) -> None:
        self._run_hooks(
            job_registry.before_perform_callbacks
            + self.__class__.before_perform_callbacks
        )

    def _run_after_perform_hooks(self) -> None:
        self._run_hooks(
            job_registry.after_perform_callbacks
            + self.__class__.after_perform_callbacks
        )

    def _run_on_success_hooks(self) -> None:
        self._run_hooks(
            job_registry.on_success_callbacks + self.__class__.on_success_callbacks
        )

    def _run_on_error_hooks(self, exc: Exception) -> None:
        self._run_hooks(
            job_registry.on_error_callbacks + self.__class__.on_error_callbacks,
            exc,
        )

    def before_perform(self) -> None: ...
    def after_perform(self) -> None: ...
    def on_success(self) -> None: ...
    def on_error(self, exc: Exception) -> None: ...

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self._run_before_perform_hooks()
        self.before_perform()

        try:
            result = self.perform(*args, **kwargs)
        except Exception as exc:
            self._run_on_error_hooks(exc)

            try:
                self.on_error(exc)
            except Exception:
                self.logger.exception("Job.on_error raised during exception handling")
            raise
        else:
            self._run_on_success_hooks()
            self.on_success()
            return result
        finally:
            self._run_after_perform_hooks()
            self.after_perform()


class JobProxy:
    """
    Proxy object returned by BaseJob.set() to carry scheduling options for perform_later()
    """

    def __init__(self, job_cls: Type[BaseJob], **opts):
        self._cls = job_cls
        self._opts = {k: v for k, v in opts.items() if v is not None}

    def perform_later(self, *args: Any, **kwargs: Any) -> JobHandle:
        nargs = [normalize_job_arg(a) for a in args]
        nkwargs = {k: normalize_job_arg(v) for k, v in kwargs.items()}
        record = get_adapter().enqueue(
            self._cls, args=nargs, kwargs=nkwargs, **self._opts
        )

        return JobHandle(record)
