from enum import StrEnum


class JobStatus(StrEnum):
    """
    Enumeration of possible job statuses.

    Stored as a string in the database for readability and ease of querying.

    Attributes:
        PENDING (str, "pending"): The job is created but not yet enqueued.
        ENQUEUED (str, "enqueued"): The job is enqueued and waiting
            to be picked up by a worker.
        RUNNING (str, "running"): The job is currently being executed by a worker.
        DONE (str, "done"): The job completed successfully.
        FAILED (str, "failed"): The job raised an exception during execution.
        RETRYING (str, "retrying"): The job failed but is scheduled to be retried.
        DISCARDED (str, "discarded"): The job failed and will not
    """

    PENDING = "pending"
    ENQUEUED = "enqueued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"
    DISCARDED = "discarded"
