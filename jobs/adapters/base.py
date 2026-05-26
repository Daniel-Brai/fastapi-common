from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Type

from lib.jobs.base import BaseJob
from lib.jobs.schemas import JobKq


class AbstractAdapter(ABC):
    """
    Adapter interface for job scheduling and execution
    """

    @abstractmethod
    def name(self) -> str:
        """
        Return a string identifier for this adapter type, e.g. "celery", "rq", etc.
        """
        raise NotImplementedError("name() must be implemented by subclasses")

    @abstractmethod
    def enqueue(
        self,
        job_cls: Type[BaseJob],
        *,
        args: list,
        kwargs: dict,
        wait: timedelta | None = None,
        wait_until: datetime | None = None
    ) -> JobKq:
        raise NotImplementedError("enqueue() must be implemented by subclasses")

    @abstractmethod
    def start(self) -> Any:
        """
        Start background workers. No-op for external adapters like Celery.
        """
        raise NotImplementedError("start() must be implemented by subclasses")

    @abstractmethod
    def stop(self) -> None:
        """
        Stop background workers. No-op for external adapters like Celery.
        """
        raise NotImplementedError("stop() must be implemented by subclasses")
