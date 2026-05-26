from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import VARCHAR, Column, Field, SQLModel

from lib.jobs.enums import JobStatus


class Job(SQLModel, table=True):
    """
        Represents a job in the queue in a database
    cls
        Attributes:
            id (int): Primary key, auto-incremented
            job_id (str): Stable UUID for the job, used for retries
            job_class (str): Fully qualified name of the job class to execute
            queue_name (str): Name of the queue this job belongs to
            priority (int): Priority of the job, higher numbers indicate higher priority
            args (list[Any]): Positional arguments for the job, stored as JSON
            kwargs (dict[Any, Any]): Keyword arguments for the job, stored as JSON
            status (JobStatus): Current status of the job (e.g., pending, in_progress, completed, failed)
            recurring (bool): Whether this job is recurring or one-time
            schedule_id (str | None): APScheduler job ID for recurring jobs
            attempts (int): Number of attempts made to execute the job
            max_attempts (int): Maximum number of attempts before marking the job as failed
            error (str | None): Error message if the job failed
            enqueued_at (datetime): Timestamp when the job was enqueued (UTC)
            scheduled_at (datetime): Timestamp when the job is scheduled to run (UTC)
            started_at (datetime | None): Timestamp when the job started execution (UTC)
            finished_at (datetime | None): Timestamp when the job finished execution (UTC)
    """

    __tablename__ = "job_queues"  # type: ignore[override]

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)  # stable uuid across retries
    job_class: str = Field(index=True)  # FQN, e.g. "myapp.jobs.SendEmailJob"
    queue_name: str = Field(default="default", index=True)
    priority: int = Field(default=0)

    args: list[Any] = Field(default_factory=list, sa_column=Column(JSONB))
    kwargs: dict[Any, Any] = Field(default_factory=dict, sa_column=Column(JSONB))

    status: JobStatus = Field(sa_column=Column(VARCHAR(20), nullable=False, index=True, default=JobStatus.PENDING))

    recurring: bool = Field(default=False, index=True)
    schedule_id: str | None = Field(default=None)  # APScheduler job id

    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    error: str | None = Field(default=None)

    enqueued_at: datetime = Field(default_factory=datetime.utcnow)
    scheduled_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
