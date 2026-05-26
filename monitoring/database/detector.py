from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from lib.monitoring.database.reporter import default_reporter
from lib.monitoring.database.schemas import CapturedQuery, N1Violation, QueryLog


@dataclass
class DetectorConfig:
    # Minimum number of identical query templates to flag as N+1
    threshold: int = 3

    # Ignore queries whose normalized SQL matches any of these substrings
    # (useful for cheap lookup tables you deliberately load per-row)
    allowlist_patterns: list[str] = field(default_factory=list)

    # Called when violations are found; defaults to stderr logging
    on_violation: Callable[[list[N1Violation]], None] | None = None


class N1Detector:
    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()

    def analyse(self, log: QueryLog) -> list[N1Violation]:
        groups: dict[str, list[CapturedQuery]] = defaultdict(list)
        for q in log.queries:
            if self._is_allowed(q.normalized_sql):
                continue

            groups[q.normalized_sql].append(q)

        violations: list[N1Violation] = []
        for norm_sql, queries in groups.items():
            if len(queries) >= self.config.threshold:
                violations.append(
                    N1Violation(
                        normalized_sql=norm_sql,
                        count=len(queries),
                        first_stack=queries[0].stack,
                        all_stacks=[q.stack for q in queries],
                        total_duration_ms=sum(q.duration_ms for q in queries),
                    )
                )

        violations.sort(key=lambda v: v.count, reverse=True)

        if violations and self.config.on_violation:
            self.config.on_violation(violations)
        elif violations:
            default_reporter(violations)

        return violations

    def _is_allowed(self, norm_sql: str) -> bool:
        return any(p.upper() in norm_sql for p in self.config.allowlist_patterns)
