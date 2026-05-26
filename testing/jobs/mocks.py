from typing import Any, Self


class MockJobHandle:
    """
    A mock job handle for testing purposes.

    It replaces the `JobHandle` returned by perform_later() in tests.
    """

    def with_session(self, session: Any) -> Self:  # noqa: ARG001
        return self
