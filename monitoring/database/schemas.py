import time
from dataclasses import dataclass, field


@dataclass
class CapturedQuery:
    """
    Schema for a single captured SQL query, including its raw and normalized forms,
    parameters, execution duration, and stack trace.
    """

    raw_sql: str
    normalized_sql: str
    params: object
    duration_ms: float
    stack: list[str]
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class N1Violation:
    """
    Schema for detected N+1 query patterns.
    """

    normalized_sql: str
    count: int
    first_stack: list[str]
    all_stacks: list[list[str]]
    total_duration_ms: float

    def __str__(self) -> str:
        location = self._fmt_stack(self.first_stack)
        return (
            f"N+1 detected: query executed {self.count}× in one request\n"
            f"  Template : {self.normalized_sql[:120]}\n"
            f"  Total ms : {self.total_duration_ms:.1f}\n"
            f"  Origin   :\n{location}"
        )

    def _fmt_stack(self, frames: list[str]) -> str:
        if not frames:
            return "    (stack unavailable)"
        return "\n".join(frames[-5:])


class QueryLog:
    """
    Collects all queries for a single request
    """

    def __init__(self) -> None:
        self.queries: list[CapturedQuery] = []
        self._start = time.monotonic()

    def record(self, q: CapturedQuery) -> None:
        self.queries.append(q)

    @property
    def total_duration_ms(self) -> float:
        return (time.monotonic() - self._start) * 1000

    @property
    def count(self) -> int:
        return len(self.queries)
