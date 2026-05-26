import uuid
from datetime import datetime, timedelta
from typing import Type

from lib.jobs.adapters.base import AbstractAdapter
from lib.jobs.base import BaseJob
from lib.jobs.enums import JobStatus
from lib.jobs.exceptions import JobConfigurationError, JobNotFoundError
from lib.jobs.registry import job_registry
from lib.jobs.schedule import CronSchedule, IntervalSchedule, OnceAt
from lib.jobs.schemas import JobKq
from lib.jobs.types import JobSchedule
from lib.jobs.utils import fqn
from lib.logger import get_logger

logger = get_logger("lib.jobs.adapters.celery")

try:
    from celery import Celery

    _celery_available = True
except ImportError:
    _celery_available = False


class CeleryAdapter(AbstractAdapter):
    """
    Celery adapter for bridging BaseJob with Celery tasks.

    A single registered task `jobs.dispatch_job` receives the job's FQN and
    serialised args/kwargs, then reconstructs and calls perform(). Job code
    never imports Celery.

    Recurring jobs are registered as Celery beat entries if `beat_schedule`
    is passed, or auto-built from BaseJob.schedule if use_beat=True.

    Examples:

        ###### Without beat:
        from celery import Celery
        celery = Celery("myapp", broker="redis://localhost:6379/0")
        configure_jobs(CeleryAdapter(celery_app=celery), modules=["myapp.jobs"])

        ###### With beat:
            configure_jobs(CeleryAdapter(celery_app=celery, use_beat=True), modules=["myapp.jobs"])
    """

    def __init__(
        self,
        celery_app: "Celery",  # type: ignore[name-defined]
        *,
        default_queue: str = "default",
        use_beat: bool = False,
    ):

        if not _celery_available:
            raise ImportError("celery is not installed. pip install celery")

        self._app = celery_app
        self._default_queue = default_queue
        self._use_beat = use_beat
        self._task = self._register_dispatch_task()

    def _register_dispatch_task(self):
        @self._app.task(name="jobs.dispatch_job", bind=True, max_retries=None)
        def dispatch_job(task, job_class_name: str, args: list, kwargs: dict):

            try:
                job_cls = job_registry.resolve(job_class_name)
                max_retries = max(0, job_cls.max_attempts - 1)
                retry_on = job_cls.retry_on
            except JobNotFoundError:
                logger.error(
                    "CeleryAdapter: Job class not found: %s",
                    job_class_name,
                    exc_info=True,
                )
                return

            job = job_cls()

            try:
                job.execute(*args, **kwargs)
            except Exception as exc:
                eligible = (not retry_on) or isinstance(exc, retry_on)
                if eligible and task.request.retries < max_retries:
                    backoff = 10 * (2**task.request.retries)
                    raise task.retry(
                        exc=exc, countdown=backoff, max_retries=max_retries
                    )

                raise exc

        return dispatch_job

    def name(self) -> str:
        return "celery"

    @property
    def is_beat_enabled(self) -> bool:
        return self._use_beat

    def enqueue(
        self,
        job_cls: Type[BaseJob],
        *,
        args: list,
        kwargs: dict,
        wait: timedelta | None = None,
        wait_until: datetime | None = None,
    ) -> JobKq:

        eta = wait_until or (datetime.now() + wait if wait else None)
        if eta:
            self._task.apply_async(
                args=(fqn(job_cls), args, kwargs),
                queue=job_cls.queue or self._default_queue,
                priority=job_cls.priority,
                eta=eta,
                compression="zlib",
            )
        else:
            self._task.apply_async(
                args=(fqn(job_cls), args, kwargs),
                queue=job_cls.queue or self._default_queue,
                priority=job_cls.priority,
                compression="zlib",
            )

        return JobKq(
            id=None,
            job_id=str(uuid.uuid7()),
            job_class=fqn(job_cls),
            queue_name=job_cls.queue,
            args=args,
            kwargs=kwargs,
            status=JobStatus.ENQUEUED,
        )

    def start(self):
        for _, job_cls in job_registry.jobs.items():
            sched: JobSchedule | None = getattr(job_cls, "schedule", None)
            if sched is None:
                logger.info(
                    "CeleryAdapter: Registered job: %s (manual queue: %s)",
                    job_cls.__name__,
                    job_cls.queue or self._default_queue,
                )
                continue

            if not self._use_beat:
                logger.info(
                    "CeleryAdapter: Registered recurring job %s but beat is disabled",
                    job_cls.__name__,
                )

        if not self._use_beat:
            return self._app

        beat_schedule = {}

        for name, job_cls in job_registry.jobs.items():
            sched: JobSchedule | None = getattr(job_cls, "schedule", None)
            if sched is None:
                continue

            beat_schedule[f"recurring__{name}"] = {
                "task": "jobs.dispatch_job",
                "schedule": self._to_celery_schedule(sched),
                "args": [fqn(job_cls), [], {}],
                "options": {"queue": job_cls.queue or self._default_queue},
            }
            logger.info(
                "CeleryAdapter: Registered Celery beat recurring job: %s",
                job_cls.__name__,
            )

        self._app.conf.beat_schedule.update(beat_schedule)

        return self._app

    def stop(self) -> None:
        pass

    @staticmethod
    def _to_celery_schedule(sched):
        from celery.schedules import crontab, schedule

        if isinstance(sched, CronSchedule):
            if sched.expr:
                minute, hour, day, month, dow = sched.expr.split()
                return crontab(
                    minute=minute,
                    hour=hour,
                    day_of_month=day,
                    month_of_year=month,
                    day_of_week=dow,
                )
            return crontab(
                minute=sched.minute,
                hour=sched.hour,
                day_of_month=sched.day,
                month_of_year=sched.month,
                day_of_week=sched.day_of_week,
            )
        if isinstance(sched, IntervalSchedule):
            total_seconds = (
                sched.weeks * 604800
                + sched.days * 86400
                + sched.hours * 3600
                + sched.minutes * 60
                + sched.seconds
            )
            return schedule(run_every=timedelta(seconds=total_seconds))
        if isinstance(sched, OnceAt):
            # NOTE: Celery Beat has no native "once" trigger; use a 100-year interval
            # # and rely on the task to self-revoke after first run.
            return timedelta(days=365 * 100)

        raise JobConfigurationError(f"Unsupported schedule type: {type(sched)}")
