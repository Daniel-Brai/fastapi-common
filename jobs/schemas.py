from dataclasses import dataclass
from typing import Any, Callable, Self

from lib.jobs.enums import JobStatus


@dataclass
class JobKq:
    """
    Schema for a job kickoff, used for both enqueuing and scheduling jobs.
    """

    id: int | None
    job_id: str
    job_class: str
    queue_name: str | None
    args: list
    kwargs: dict
    status: JobStatus

    @classmethod
    def from_job(cls, job: Any) -> Self:
        return cls(
            id=job.id,
            job_id=job.job_id,
            job_class=job.job_class,
            queue_name=job.queue_name,
            args=job.args,
            kwargs=job.kwargs,
            status=job.status,
        )


@dataclass
class Shim:
    """
    A single migration step applied to (args, kwargs) before perform().

    Shims are useful for when using the db adapter, but for celery adapter, there is no need for shims

    `when`:     predicate that returns True if this shim should fire.
                Receives the raw (args, kwargs) as stored in the DB.
    `apply`:    transforms (args, kwargs) into the shape the current
                perform() signature expects. Must return (args, kwargs).

    Shims are applied in the order they appear in `BaseJob.migrations`.
    Each shim sees the output of the previous one, so they chain naturally.

    Examples:

        # Rename a kwarg from "user_id" to "account_id"
        Shim(
            when  = lambda a, kw: "user_id" in kw and "account_id" not in kw,
            apply = lambda a, kw: (a, {**kw, "account_id": kw.pop("user_id")}),
        )

        # Positional args to kwargs
        Shim(
            when  = lambda a, kw: len(a) >= 2 and not kw,
            apply = lambda a, kw: ([], {"user_id": a[0], "template": a[1]}),
        )

        # Backfilling a new optional field with a default value
        Shim(
            when  = lambda a, kw: "locale" not in kw,
            apply = lambda a, kw: (a, {**kw, "locale": "en"}),
        )

        # Adding a new required field with a default value is also possible, but be cautious as this can have unintended consequences.
        # It's often better to make new fields optional and handle defaults in the perform() method.
        Shim(
            when  = lambda a, kw: "priority" not in kw,
            apply = lambda a, kw: (a, {**kw, "priority": "normal"}),
        )

        # Removing an arg that's no longer needed
        Shim(
            when  = lambda a, kw: len(a) >= 1 and a[0] == "deprecated_value",
            apply = lambda a, kw: (a[1:], kw),
        )

        # Complex transformations are of course possible
        Shim(
            when  = lambda a, kw: "version" in kw and kw["version"] == 1,
            apply = lambda a, kw: (
                a[1:] + [kw.pop("new_arg")],
                {**kw, "version": 2}
            ),
        )
    """

    when: Callable[[list, dict], bool]
    apply: Callable[[list, dict], tuple[list, dict]]
