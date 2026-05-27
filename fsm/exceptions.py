class StateError(Exception):
    """
    Base exception for all FSM State errors
    """


class InvalidStateError(StateError):
    """
    Raised when an unknown or duplicate state is declared
    """


class InvalidTransitionError(StateError):
    """
    Raised when a transition references non-existent states
    """


class InvalidCallbackError(StateError):
    """
    Raised when a callback is registered without a callable
    """


class GuardFailedError(StateError):
    """
    Raised when a guard returns a falsy value, preventing a transition from occurring.
    """

    def __init__(self, from_state: str | None, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Guard failed: cannot transition from '{from_state}' to '{to_state}'"
        )


class TransitionFailedError(StateError):
    """
    Raised when the requested transition is not defined
    """

    def __init__(self, from_state: str | None, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state

        super().__init__(
            f"Transition '{from_state}' to '{to_state}' is not defined"
        )


class TransitionConflictError(StateError):
    """
    Raised when a database-level conflict occurs (e.g. duplicate `sort_key`)
    """


class MissingTransitionAssociation(StateError):
    """
    Raised when the adapter cannot find the transition relationship.
    """