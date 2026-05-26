from typing import Any, Type

from .mocks import MockJobHandle


class DispatchedJob:
    """
    A recorded job dispatch for testing purposes.
    """

    def __init__(
        self,
        job_class: Type[Any],
        args: list[Any],
        kwargs: dict[str, Any],
        mode: str,
    ) -> None:
        self.job_class = job_class
        self.args = args
        self.kwargs = kwargs
        self.mode = mode
        self.handle = MockJobHandle()

    def __repr__(self) -> str:
        return f"<DispatchedJob {self.job_class.__name__} " f"mode={self.mode} args={self.args} kwargs={self.kwargs}>"
