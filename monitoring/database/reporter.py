import sys

from lib.logger import get_logger
from lib.monitoring.database.schemas import N1Violation

logger = get_logger(__name__)


def default_reporter(violations: list[N1Violation]) -> None:
    """
    Report detected N+1 violations to stderr with a human-friendly format.
    """

    use_color = sys.stderr.isatty()
    RED = "\033[31m" if use_color else ""
    YELLOW = "\033[33m" if use_color else ""
    RESET = "\033[0m" if use_color else ""
    BOLD = "\033[1m" if use_color else ""

    sep = "─" * 72
    print(
        f"\n{RED}{BOLD}[fastapi-nplusone] {len(violations)} N+1 violation(s) detected{RESET}",
        file=sys.stderr,
    )
    for i, v in enumerate(violations, 1):
        print(f"{YELLOW}{sep}{RESET}", file=sys.stderr)
        print(
            f"{BOLD}#{i}  {v.count}x executions  ({v.total_duration_ms:.1f} ms total){RESET}",
            file=sys.stderr,
        )
        print(f"Query template:\n  {v.normalized_sql[:200]}", file=sys.stderr)
        print("Originated from:", file=sys.stderr)
        for line in v.first_stack[-6:]:
            print(line, file=sys.stderr)

    print(f"{YELLOW}{sep}{RESET}\n", file=sys.stderr)
