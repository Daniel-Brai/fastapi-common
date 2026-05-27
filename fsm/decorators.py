from typing import Callable
from .helpers import attach


_GUARD_MARKER         = "_fsm_guards"
_BEFORE_MARKER        = "_fsm_before"
_AFTER_MARKER         = "_fsm_after"
_AFTER_FAIL_MARKER    = "_fsm_after_failure"
_AFTER_GUARD_MARKER   = "_fsm_after_guard_failure"


def guard_transition(
    *,
    from_state: str | None = None,
    to: str | None = None,
) -> Callable:
    """
    Register a guard on a state machine method

    The decorated method receives ``(self, model)`` and **must** return a
    truthy value to allow the transition.  Both sync and async definitions
    are supported::

        @guard_transition(to="checking_out")
        def ensure_products_in_stock(self, order):
            return order.has_stock()

        @guard_transition(from_state="checking_out", to="cancelled")
        async def ensure_cancellable(self, order):
            return await order.can_cancel_async()

    Omitting a parameter means "match any":

    - ``guard_transition(to="purchased")``      → guard all transitions *to* purchased
    - ``guard_transition()``                     → guard *all* transitions
    """

    def decorator(func: Callable) -> Callable:
        return attach(func, _GUARD_MARKER, {"from_state": from_state, "to": to})

    return decorator


def before_transition(
    *,
    from_state: str | None = None,
    to: str | None = None,
) -> Callable:
    """
    Register a before-transition callback

    It runs after guards pass but *before* the transition is persisted.

    It receives ``(self, model, transition: TransitionRecord)`` and can be sync or async.
    """

    def decorator(func: Callable) -> Callable:
        return attach(func, _BEFORE_MARKER, {"from_state": from_state, "to": to})

    return decorator


def after_transition(
    *,
    from_state: str | None = None,
    to: str | None = None,
    after_commit: bool = False,
) -> Callable:
    """
    Register an after-transition callback

    It runs after the transition is persisted.
    
    It receives ``(self, model: Any, transition: TransitionRecord)`` and can be sync or async.

    It passes ``after_commit=True`` to defer execution until after the DB transaction commits.  
    
    Hence, one must call ``await machine.run_after_commit_callbacks(record)`` yourself after
    committing.
    """

    def decorator(func: Callable) -> Callable:
        return attach(func, _AFTER_MARKER, {
            "from_state": from_state,
            "to": to,
            "after_commit": after_commit,
        })

    return decorator


def after_transition_failure(
    *,
    from_state: str | None = None,
    to: str | None = None,
) -> Callable:
    """
    Register a callback that fires when a ``TransitionFailedError`` is raised
    during a transition's callback phase.

    It receives ``(self, model: Any, exception: Exception)``.
    """

    def decorator(func: Callable) -> Callable:
        return attach(func, _AFTER_FAIL_MARKER, {"from_state": from_state, "to": to})

    return decorator


def after_guard_failure(
    *,
    from_state: str | None = None,
    to: str | None = None,
) -> Callable:
    """
    Register a callback that fires when a ``GuardFailedError`` is raised.

    Receives ``(self, model: Any, exception: Exception)``.
    """

    def decorator(func: Callable) -> Callable:
        return attach(func, _AFTER_GUARD_MARKER, {"from_state": from_state, "to": to})

    return decorator