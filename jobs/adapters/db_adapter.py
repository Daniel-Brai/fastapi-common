import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Type

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPool
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session
from sqlmodel import col, select

from lib.jobs.adapters.base import AbstractAdapter
from lib.jobs.base import BaseJob
from lib.jobs.config import get_job_queues, get_registry
from lib.jobs.enums import JobStatus
from lib.jobs.exceptions import JobNotFoundError
from lib.jobs.models import Job
from lib.jobs.schemas import JobKq
from lib.jobs.utils import fqn
from lib.logger import get_logger

logger = get_logger("lib.jobs.adapters.db")

STALE_RUNNING_TIMEOUT = timedelta(minutes=30)


class DBAdapter(AbstractAdapter):
    """
    Database-backed adapter powered by APScheduler's BackgroundScheduler.

    APScheduler drives three categories of work:
      1. Poll loop  — drains enqueued/retrying rows every `poll_interval` seconds.
      2. Sweeper    — resets stale "running" rows every `sweep_interval` seconds.
      3. Recurring  — one APScheduler job per BaseJob subclass with a .schedule.

    Job claiming uses SELECT FOR UPDATE SKIP LOCKED on supported databases
    (PostgreSQL, MySQL 8+, MariaDB 10.6+) so two workers can never receive
    the same job. Falls back to optimistic status-flip on SQLite (dev only).

    All actual execution runs in a ThreadPoolExecutor so the scheduler thread
    is never blocked by job work.

    Examples:
        configure_jobs(DBAdapter(engine=engine, workers=4), modules=["myapp.jobs"])
    """

    def __init__(
        self,
        engine: Engine,
        *,
        workers: int = 4,
        poll_interval: float = 2.0,
        sweep_interval: float = 60.0,
        queues: List[str] | None = None,
    ):
        self._engine = engine
        self._workers = workers
        self._poll_interval = poll_interval
        self._sweep_interval = sweep_interval
        self._queues_init = queues
        self._queues = None
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="job-worker"
        )
        self._scheduler = self._build_scheduler()
        self._skip_locked = self._detect_skip_locked()

        if not self._skip_locked:
            logger.warning(
                "DBAdapter: %s does not support SELECT FOR UPDATE SKIP LOCKED. "
                "Falling back to optimistic status-flip. "
                "Use PostgreSQL or MySQL 8+ in production to prevent double-execution.",
                self._engine.dialect.name,
            )

    def _detect_skip_locked(self) -> bool:
        """
        Helper to detect if the connected database supports `SELECT FOR UPDATE SKIP LOCKED`.
        """

        return self._engine.dialect.name in ("postgresql", "mysql", "mariadb")

    def _build_scheduler(self) -> BackgroundScheduler:
        """
        It uses an in-memory job store for APScheduler's internal schedule.

        The durable job state lives in the `Job` table;

        APScheduler is only a tick source here, so memory is sufficient and avoids pickling the SQLAlchemy engine on scheduler startup.
        """

        return BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": APSThreadPool(max_workers=1)},
            timezone="UTC",
        )

    def name(self) -> str:
        return "db"

    def start(self) -> None:
        self._queues = (
            self._queues_init if self._queues_init is not None else get_job_queues()
        )

        self._scheduler.add_job(
            self._poll_and_dispatch,
            trigger="interval",
            seconds=self._poll_interval,
            id="__poll__",
            replace_existing=True,
            name="[internal] drain queue",
            misfire_grace_time=int(self._poll_interval * 2),
        )
        self._scheduler.add_job(
            self._sweep_stale,
            trigger="interval",
            seconds=self._sweep_interval,
            id="__sweep__",
            replace_existing=True,
            name="[internal] stale sweeper",
            misfire_grace_time=int(self._sweep_interval * 2),
        )

        self._register_recurring_jobs()
        self._scheduler.add_listener(self._on_scheduler_error, EVENT_JOB_ERROR)
        self._scheduler.start()

        logger.info(
            "DBAdapter: Started (%d workers, %.1fs poll, %.1fs sweep, skip_locked=%s)",
            self._workers,
            self._poll_interval,
            self._sweep_interval,
            self._skip_locked,
        )

    def stop(self) -> None:
        self._scheduler.shutdown(wait=True)
        self._executor.shutdown(wait=True)

        if getattr(self, "_engine", None) is not None:
            self._engine.dispose()

        logger.info("DBAdapter: Stopped gracefully")

    @staticmethod
    def _on_scheduler_error(event) -> None:
        logger.exception(
            "DBAdapter: APScheduler internal error in job %s: %s",
            event.job_id,
            event.exception,
        )

    def enqueue(
        self,
        job_cls: Type[BaseJob],
        *,
        args: list,
        kwargs: dict,
        wait=None,
        wait_until=None,
    ) -> JobKq:
        scheduled_at = wait_until or (datetime.now() + wait if wait else datetime.now())
        record = Job(
            job_id=str(uuid.uuid7()),
            job_class=fqn(job_cls),
            queue_name=job_cls.queue,
            priority=job_cls.priority,
            max_attempts=job_cls.max_attempts,
            args=args,
            kwargs=kwargs,
            status=JobStatus.ENQUEUED,
            scheduled_at=scheduled_at,
            recurring=bool(job_cls.schedule),
        )
        with Session(self._engine) as s:
            s.add(record)
            s.commit()
            s.refresh(record)

        logger.debug(
            "DBAdapter: Enqueued %s id=%s (scheduled_at=%s)",
            record.job_class,
            record.job_id,
            record.scheduled_at,
        )
        return JobKq.from_job(record)

    def enlist(self, record_id: int | None, session: Session) -> None:
        """
        Enlist a pending Job into the caller's session so it commits atomically with the surrounding business transaction.

        It marks the row PENDING (invisible to the poller) until the caller's
        transaction commits at which point it is promoted to `ENQUEUED`.

        On rollback the row is deleted entirely.
        """

        record = session.get(Job, record_id)
        if not record:
            logger.error(
                "DBAdapter: Failed to enlist job id=%s: record not found in session",
                record_id,
            )
            return

        record.status = JobStatus.PENDING
        merged = session.merge(record)

        @event.listens_for(session, "after_commit", once=True)
        def _promote(_session):
            with Session(self._engine) as s:
                r = s.get(Job, merged.id)
                if r and r.status == JobStatus.PENDING:
                    r.status = JobStatus.ENQUEUED
                    s.commit()

        @event.listens_for(session, "after_rollback", once=True)
        def _discard(_session):
            with Session(self._engine) as s:
                r = s.get(Job, merged.id)
                if r:
                    s.delete(r)
                    s.commit()

            logger.debug(
                "DBAdapter: Rolled back job %s id=%s",
                record.job_class,
                record.job_id,
            )

    def _poll_and_dispatch(self) -> None:
        """
        Claim up to `workers` eligible rows atomically and dispatch to the pool.

        - With SKIP LOCKED (PostgreSQL / MySQL 8+):
            The SELECT and UPDATE run inside a single transaction.
            Rows already locked by another worker are silently skipped —
            two workers can never receive the same job even under full
            concurrency. No blocking, no deadlocks.

        - Without SKIP LOCKED (SQLite / fallback):
            Optimistic status-flip: status is set to RUNNING before commit.
            A small race window exists between SELECT and UPDATE; acceptable
            only in development / single-worker setups.
        """

        with Session(self._engine) as s:
            q = (
                select(Job)
                .where(col(Job.status).in_([JobStatus.ENQUEUED, JobStatus.RETRYING]))
                .where(col(Job.scheduled_at) <= datetime.now())
            )

            if self._queues:
                q = q.where(col(Job.queue_name).in_(self._queues))

            q = q.order_by(col(Job.priority).desc(), col(Job.scheduled_at)).limit(
                self._workers
            )

            if self._skip_locked:
                # Lock selected rows for the duration of this transaction.
                # Rows already locked by a concurrent worker are skipped entirely
                q = q.with_for_update(skip_locked=True)

            records = s.execute(q).scalars().all()

            for r in records:
                r.status = JobStatus.RUNNING
                r.started_at = datetime.now()
                s.add(r)

            # Commit releases the FOR UPDATE locks.
            # Rows are now RUNNING and invisible to all other pollers.
            s.commit()

            ids = [r.id for r in records]

        for record_id in ids:
            if record_id is None:
                continue

            self._executor.submit(self._run_job, record_id)

    def _sweep_stale(self) -> None:
        """
        Resets jobs stuck in RUNNING longer than `STALE_RUNNING_TIMEOUT` back to `RETRYING` so the poll loop reclaims them.

        A job becomes stale when the worker thread/process is killed
        (SIGKILL, OOM, machine failure) without having updated the record.

        Jobs that have exhausted retries are marked FAILED instead.
        """

        cutoff = datetime.now() - STALE_RUNNING_TIMEOUT

        with Session(self._engine) as s:
            stale = (
                s.execute(
                    select(Job)
                    .where(col(Job.status) == JobStatus.RUNNING)
                    .where(col(Job.started_at) <= cutoff)
                )
                .scalars()
                .all()
            )

            for r in stale:
                if r.attempts >= r.max_attempts:
                    r.status = JobStatus.FAILED
                    r.finished_at = datetime.now()
                    r.error = (
                        f"Permanently failed: job exceeded max_attempts ({r.max_attempts}) "
                        f"after being marked stale at {cutoff.isoformat()}"
                    )
                    logger.error(
                        "DBAdapter: Sweeper permanently failed stale job %s id=%s",
                        r.job_class,
                        r.job_id,
                    )
                else:
                    backoff = 10 * (2**r.attempts)
                    r.status = JobStatus.RETRYING
                    r.scheduled_at = datetime.now() + timedelta(seconds=backoff)
                    logger.warning(
                        "DBAdapter: Sweeper reset stale job %s id=%s "
                        "→ retrying in %ds (attempt %d/%d)",
                        r.job_class,
                        r.job_id,
                        backoff,
                        r.attempts,
                        r.max_attempts,
                    )
                s.add(r)

            s.commit()

        if stale:
            logger.info("DBAdapter: Sweeper processed %d stale job(s)", len(stale))

    def _run_job(self, record_id: int) -> None:
        with Session(self._engine) as s:
            record = s.get(Job, record_id)
            if not record:
                return

            try:
                job_cls = get_registry().resolve(record.job_class)
            except JobNotFoundError:
                logger.error(
                    "DBAdapter: Failed to resolve job class %s for job id=%s",
                    record.job_class,
                    record.job_id,
                )
                return

            job = job_cls()
            record.attempts += 1
            args, kwargs = job_cls.migrate(record.args, record.kwargs)

            try:
                job.execute(*args, **kwargs)

                if job_cls.discard_on_success:
                    s.delete(record)
                    logger.debug(
                        "DBAdapter: Completed and discarded %s id=%s",
                        record.job_class,
                        record.job_id,
                    )
                else:
                    record.status = JobStatus.DONE
                    record.finished_at = datetime.now()
                    s.add(record)
                    logger.debug(
                        "DBAdapter: Completed %s id=%s",
                        record.job_class,
                        record.job_id,
                    )

            except Exception as exc:
                record.error = traceback.format_exc()
                retry_on = job_cls.retry_on
                eligible = (
                    (not retry_on)
                    or isinstance(exc, retry_on)
                    or issubclass(type(exc), retry_on)
                )

                if not eligible:
                    record.status = JobStatus.FAILED
                    record.finished_at = datetime.now()
                    logger.error(
                        "DBAdapter: Failed immediately (exception not in retry_on) "
                        "%s id=%s: %s",
                        record.job_class,
                        record.job_id,
                        type(exc).__name__,
                        exc_info=True,
                    )
                elif record.attempts >= record.max_attempts:
                    record.status = JobStatus.FAILED
                    record.finished_at = datetime.now()
                    logger.error(
                        "DBAdapter: Permanently failed %s id=%s after %d attempts",
                        record.job_class,
                        record.job_id,
                        record.attempts,
                        exc_info=True,
                    )
                else:
                    backoff = 10 * (2**record.attempts)
                    record.status = JobStatus.RETRYING
                    record.scheduled_at = datetime.now() + timedelta(seconds=backoff)
                    logger.warning(
                        "DBAdapter: Retrying %s id=%s in %ds (attempt %d/%d)",
                        record.job_class,
                        record.job_id,
                        backoff,
                        record.attempts,
                        record.max_attempts,
                    )

                s.add(record)

            s.commit()

    def _register_recurring_jobs(self) -> None:
        """
        Walk every registered job class.

        If it carries a `.schedule`, register a corresponding APScheduler job that calls perform_later() on each tick.
        """

        unregistered = 0

        for name, job_cls in get_registry().jobs.items():
            sched = job_cls.schedule
            if sched is None:
                unregistered += 1

                logger.info(
                    "DBAdapter: Registered job: %s (manual queue: %s)",
                    job_cls.__name__,
                    job_cls.queue or "default",
                )
                continue

            aps_kwargs = sched.as_apscheduler_kwargs()
            scheduler_id = f"recurring__{name}"

            def _fire(cls=job_cls):
                cls.perform_later()

            self._scheduler.add_job(
                _fire,
                id=scheduler_id,
                name=f"[recurring] {job_cls.__name__}",
                replace_existing=True,
                misfire_grace_time=60,
                **aps_kwargs,
            )

            logger.info(
                "DBAdapter: Registered recurring job: %s (%s) (queue: %s)",
                job_cls.__name__,
                aps_kwargs["trigger"],
                job_cls.queue or "default",
            )
