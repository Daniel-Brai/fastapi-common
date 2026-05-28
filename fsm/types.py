from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable


@dataclass
class StateDefinition:
    """
    Structure representing a state definition within the FSM.

    Attributes:
        name (str): The unique name of the state.
        initial (bool): Indicates if this state is the initial state of the FSM. Defaults to False.
    """

    name: str
    initial: bool = False


@dataclass
class TransitionDefinition:
    """
    Structure representing a transition definition within the FSM.

    Attributes:
        from_state (str): The name of the state from which the transition originates.
        to_states (list[str]): A list of state names to which the transition can occur.
    """


    from_state: str
    to_states: list[str]

    def allows_to(self, state: str) -> bool:
        """
        Check if this transition definition allows transitioning to the specified state.

        Args:
            state (str): The name of the state to check.
        """

        return state in self.to_states


@dataclass
class TransitionRecord:
    """
    Structure representing a state transition event within the FSM.

    It is an immutable value object representing one state transition event.

    When using a database adapter the ``id`` field is populated after persistence.
    """

    from_state: str | None
    to_state: str
    metadata: dict[str, Any] = field(default_factory=dict)
    sort_key: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: Any = field(default=None, compare=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TransitionRecord("
            f"from={self.from_state!r}, "
            f"to={self.to_state!r}, "
            f"sort_key={self.sort_key})"
        )


@dataclass
class GuardDefinition:
    """
    Structure representing a guard definition within the FSM.

    Attributes:
        func (Callable): The guard function to be called during a transition.
        from_state (str | None): The name of the state from which the transition originates.
                                  If None, the guard matches any from-state.
        to_state (str | None): The name of the state to which the transition occurs.
                                If None, the guard matches any to-state.
    """

    func: Callable
    from_state: str | None 
    to_state: str | None   

    def matches(self, from_state: str | None, to_state: str) -> bool:
        """
        Check if this guard definition matches the specified from and to states.

        Args:
            from_state (str | None): The name of the state from which the transition originates.
            to_state (str): The name of the state to which the transition occurs.

        Returns:
            bool: True if the guard matches the specified states, False otherwise.
        """

        from_ok = self.from_state is None or self.from_state == from_state
        to_ok   = self.to_state   is None or self.to_state   == to_state
        return from_ok and to_ok


@dataclass
class CallbackDefinition:
    """
    Structure representing a callback definition within the FSM.

    Attributes:
        func (Callable): The callback function to be called during a transition.
        from_state (str | None): The name of the state from which the transition originates.
                                  If None, the callback matches any from-state.
        to_state (str | None): The name of the state to which the transition occurs.
                                If None, the callback matches any to-state.
        after_commit (bool): Indicates if the callback should be executed after the transition is committed.
                            Defaults to False, meaning the callback is executed before the transition is committed.
    """

    func: Callable
    from_state: str | None
    to_state: str | None
    after_commit: bool = False

    def matches(self, from_state: str | None, to_state: str) -> bool:
        """
        Check if this callback definition matches the specified from and to states.

        Args:
            from_state (str | None): The name of the state from which the transition originates.
            to_state (str): The name of the state to which the transition occurs.

        Returns:
            bool: True if the callback matches the specified states, False otherwise.
        """

        from_ok = self.from_state is None or self.from_state == from_state
        to_ok   = self.to_state   is None or self.to_state   == to_state
        return from_ok and to_ok