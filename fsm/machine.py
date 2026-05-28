from datetime import UTC, datetime
from typing import Any, Callable, TypeVar

from .namespace import MachineNamespace
from .types import (
    CallbackDefinition,
    GuardDefinition,
    StateDefinition,
    TransitionDefinition,
    TransitionRecord,
)
from .decorators import (
    _AFTER_FAIL_MARKER,
    _AFTER_GUARD_MARKER,
    _AFTER_MARKER,
    _BEFORE_MARKER,
    _GUARD_MARKER,
)
from .exceptions import (
    GuardFailedError,
    InvalidStateError,
    TransitionFailedError,
)
from .helpers import maybe_await

T = TypeVar("T")


class StateMachineMeta(type):
    """
    Metaclass that processes the DSL declarations collected by ``MachineNamespace`` and wires up all guards and callbacks.
    """

    _states: dict[str, StateDefinition]
    _transitions: list[TransitionDefinition]
    _guards: list[GuardDefinition]
    _before_cbs: list[CallbackDefinition]
    _after_cbs: list[CallbackDefinition]
    _after_failure_cbs: list[CallbackDefinition]
    _after_guard_fail_cbs: list[CallbackDefinition]

    @classmethod
    def __prepare__(mcs, name: str, bases: tuple) -> MachineNamespace:  # type: ignore[override]
        return MachineNamespace(bases)

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: MachineNamespace,
    ) -> type:
        raw_states: dict = getattr(namespace, "_states", {})
        raw_transitions: list = getattr(namespace, "_transitions", [])

        states: dict[str, StateDefinition] = {
            n: StateDefinition(name=n, initial=d["initial"])
            for n, d in raw_states.items()
        }
        transitions: list[TransitionDefinition] = [
            TransitionDefinition(from_state=t["from"], to_states=t["to"])
            for t in raw_transitions
        ]

        guards: list[GuardDefinition] = []
        before_cbs: list[CallbackDefinition] = []
        after_cbs: list[CallbackDefinition] = []
        after_failure_cbs: list[CallbackDefinition] = []
        after_guard_fail_cbs: list[CallbackDefinition] = []

        for value in namespace.values():
            if not callable(value):
                continue

            for spec in getattr(value, _GUARD_MARKER, []):
                guards.append(
                    GuardDefinition(
                        func=value,
                        from_state=spec["from_state"],
                        to_state=spec["to"],
                    )
                )

            for spec in getattr(value, _BEFORE_MARKER, []):
                before_cbs.append(
                    CallbackDefinition(
                        func=value,
                        from_state=spec["from_state"],
                        to_state=spec["to"],
                    )
                )

            for spec in getattr(value, _AFTER_MARKER, []):
                after_cbs.append(
                    CallbackDefinition(
                        func=value,
                        from_state=spec["from_state"],
                        to_state=spec["to"],
                        after_commit=spec.get("after_commit", False),
                    )
                )

            for spec in getattr(value, _AFTER_FAIL_MARKER, []):
                after_failure_cbs.append(
                    CallbackDefinition(
                        func=value,
                        from_state=spec["from_state"],
                        to_state=spec["to"],
                    )
                )

            for spec in getattr(value, _AFTER_GUARD_MARKER, []):
                after_guard_fail_cbs.append(
                    CallbackDefinition(
                        func=value,
                        from_state=spec["from_state"],
                        to_state=spec["to"],
                    )
                )

        cls = super().__new__(mcs, name, bases, namespace.to_clean_dict())

        cls._states = states
        cls._transitions = transitions
        cls._guards = guards
        cls._before_cbs = before_cbs
        cls._after_cbs = after_cbs
        cls._after_failure_cbs = after_failure_cbs
        cls._after_guard_fail_cbs = after_guard_fail_cbs

        if states:
            mcs._validate(cls, name)

        return cls

    def _validate(cls: type, class_name: str) -> None:
        initial_count = sum(1 for s in cls._states.values() if s.initial)
        if initial_count > 1:
            raise InvalidStateError(
                f"{class_name}: more than one initial state declared"
            )

        known = set(cls._states)
        for t in cls._transitions:
            if t.from_state not in known:
                raise InvalidStateError(
                    f"{class_name}: unknown state '{t.from_state}' in transition"
                )

            for to in t.to_states:
                if to not in known:
                    raise InvalidStateError(
                        f"{class_name}: unknown state '{to}' in transition"
                    )


class StateMachine(metaclass=StateMachineMeta):
    """
    Base class for all state machines.

    Subclass it and use the injected DSL inside the class body::

        from fsm import StateMachine, guard_transition, before_transition, after_transition

        class OrderStateMachine(StateMachine):
            state("pending", initial=True)
            state("checking_out")
            state("purchased")
            state("shipped")
            state("cancelled")
            state("failed")
            state("refunded")

            transition(from_state="pending",       to=["checking_out", "cancelled"])
            transition(from_state="checking_out",  to=["purchased",    "cancelled"])
            transition(from_state="purchased",     to=["shipped",      "failed"])
            transition(from_state="shipped",       to="refunded")

            @guard_transition(to="checking_out")
            def ensure_products_in_stock(self, order):
                return order.products_in_stock()

            @before_transition(from_state="checking_out", to="cancelled")
            def reallocate_stock(self, order, transition):
                order.reallocate_stock()

            @before_transition(to="purchased")
            async def charge_payment(self, order, transition):
                await PaymentService(order).submit()

            @after_transition(to="purchased")
            async def send_confirmation(self, order, transition):
                await MailerService.order_confirmation(order)

            @after_transition(to="purchased", after_commit=True)
            async def update_analytics(self, order, transition):
                # Runs only after you call run_after_commit_callbacks()
                await Analytics.record_purchase(order)

            @after_guard_failure(to="checking_out")
            def log_guard_failure(self, order, exc):
                logger.warning(f"Guard failed for order {order.id}: {exc}")

    Instantiation::

        machine = OrderStateMachine(order)                      # in-memory
        machine = OrderStateMachine(order, adapter=my_adapter)  # custom adapter
    """

    def __init__(
        self,
        model: Any,
        *,
        adapter: Any | None = None,
    ) -> None:

        from .adapters.memory import MemoryAdapter

        self._model = model
        self._adapter = adapter if adapter is not None else MemoryAdapter()

    @classmethod
    def initial_state(cls) -> str | None:
        """
        Retrieve the name of the initial state

        Returns:
            Optional[str]: The name of the initial state, or ``None`` if no initial state
        """

        for s in cls._states.values():
            if s.initial:
                return s.name

        return None

    @classmethod
    def states(cls) -> list[str]:
        """
        Retrieve a list of all state names defined in the machine.

        Returns:
            List[str]: A list of state names.
        """

        return list(cls._states.keys())

    @classmethod
    def successors(cls) -> dict[str, list[str]]:
        """
        Retrieve a mapping of each state to its valid successor states::

            {
                "pending":       ["checking_out", "cancelled"],
                "checking_out":  ["purchased",    "cancelled"],
                ...
            }
        """

        result: dict[str, list[str]] = {}
        for t in cls._transitions:
            result.setdefault(t.from_state, []).extend(t.to_states)

        return result

    @property
    def model(self) -> Any:
        """
        Retrieve the wrapped model object.
        """

        return self._model

    async def current_state(self, *, force_reload: bool = False) -> str:
        """
        Return the current state name.

        If *force_reload* is ``True``, bypass any caching and fetch the latest state from the adapter.

        Args:
            force_reload (bool): Whether to bypass caching and fetch the latest state from the adapter.

        Returns:
            str: The name of the current state.
        """

        last = await self._adapter.last_transition(force_reload=force_reload)
        if last is None:
            return self.__class__.initial_state() or ""

        return last.to_state

    async def history(self) -> list[TransitionRecord]:
        """
        Retrieve all transitions in chronological order
        """

        return await self._adapter.history()

    async def last_transition(self) -> TransitionRecord | None:
        """
        Retrieve the most recent :class:`TransitionRecord`

        Returns:
            Optional[TransitionRecord]: The most recent transition record, or ``None`` if no transitions have been made.
        """

        return await self._adapter.last_transition()

    async def last_transition_to(self, state: str) -> TransitionRecord | None:
        """
        Retrieve the most recent transition *to* the given state.

        Returns:
            Optional[TransitionRecord]: The most recent transition record, or ``None`` if no transitions have been made.
        """

        for record in reversed(await self.history()):
            if record.to_state == state:
                return record

        return None

    async def in_state(self, *states: str) -> bool:
        """
        Check whether the current state is any of *states*.

        Args:
            *states (str): One or more state names to check against the current state.

        Returns:
            bool: ``True`` if the current state matches any of *states*, ``False``
        """

        return (await self.current_state()) in states

    async def allowed_transitions(self) -> list[str]:
        """
        Retrieve a list of all states that can be transitioned to from the current state.
        """

        current = await self.current_state()
        reachable: list[str] = []

        for t in self.__class__._transitions:
            if t.from_state == current:
                reachable.extend(t.to_states)

        return reachable

    async def can_transition_to(self, state: str) -> bool:
        """
        Return ``True`` if *state* is reachable from the current state
        **and** all applicable guards pass.
        """

        if state not in await self.allowed_transitions():
            return False
        from_state = await self.current_state()
        try:
            await self._run_guards(from_state, state)
            return True
        except GuardFailedError:
            return False

    async def transition_to(
        self,
        state: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransitionRecord:
        """
        Transition to *state*, returning the persisted :class:`TransitionRecord`.

        Execution order:

        1. Validate transition is defined.
        2. Run guards → raise :exc:`GuardFailedError` on failure
           (triggers ``after_guard_failure`` callbacks).
        3. Run ``before_transition`` callbacks.
        4. Persist via adapter.
        5. Run ``after_transition`` callbacks (non-after-commit only).

        Raises:
            :exc:`TransitionFailedError`: transition not defined.
            :exc:`GuardFailedError`: a guard returned a falsy value.
        """

        from_state = await self.current_state()
        metadata = metadata or {}
        all_history = await self.history()

        if state not in await self.allowed_transitions():
            raise TransitionFailedError(from_state, state)

        record = TransitionRecord(
            from_state=from_state,
            to_state=state,
            metadata=metadata,
            sort_key=len(all_history),
            created_at=datetime.now(UTC),
        )

        try:
            await self._run_guards(from_state, state)
        except GuardFailedError as exc:
            await self._run_after_guard_fail_cbs(from_state, state, exc)
            raise

        try:
            await self._run_before_cbs(from_state, state, record)
            saved = await self._adapter.create_transition(record)
            await self._run_after_cbs(from_state, state, saved, after_commit=False)
        except (GuardFailedError, TransitionFailedError):
            raise
        except Exception as exc:
            await self._run_after_failure_cbs(from_state, state, exc)
            raise

        return saved

    async def try_transition_to(
        self,
        state: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Like :meth:`transition_to` but returns ``False`` instead of raising
        :exc:`GuardFailedError` or :exc:`TransitionFailedError`.

        Exceptions raised *inside* callbacks still propagate.
        """
        try:
            await self.transition_to(state, metadata)
            return True
        except (GuardFailedError, TransitionFailedError):
            return False

    async def run_after_commit_callbacks(self, record: TransitionRecord) -> None:
        """
        Fire ``after_commit=True`` callbacks for *record*.

        Call this after your database session commits::

            record = await machine.transition_to("purchased")
            session.commit()
            await machine.run_after_commit_callbacks(record)
        """

        await self._run_after_cbs(
            record.from_state, record.to_state, record, after_commit=True
        )


    @classmethod
    async def retry_conflicts(
        cls,
        func: Callable,
        max_retries: int = 1,
    ) -> Any:
        """
        Retry *func* up to *max_retries* times if :exc:`TransitionConflictError` is raised (e.g. due to a concurrent write in the database)::

            await OrderStateMachine.retry_conflicts(
                lambda: machine.transition_to("shipped"),
                max_retries=3,
            )
        """

        from .exceptions import TransitionConflictError

        for attempt in range(max_retries + 1):
            try:
                return await maybe_await(func())
            except TransitionConflictError:
                if attempt >= max_retries:
                    raise

    def _match_guards(
        self, from_state: str | None, to_state: str
    ) -> list[GuardDefinition]:
        return [g for g in self.__class__._guards if g.matches(from_state, to_state)]

    def _match_before(self, fs: str | None, ts: str) -> list[CallbackDefinition]:
        return [cb for cb in self.__class__._before_cbs if cb.matches(fs, ts)]

    def _match_after(
        self, fs: str | None, ts: str, *, after_commit: bool
    ) -> list[CallbackDefinition]:
        return [
            cb
            for cb in self.__class__._after_cbs
            if cb.matches(fs, ts) and cb.after_commit == after_commit
        ]

    def _match_after_failure(self, fs: str | None, ts: str) -> list[CallbackDefinition]:
        return [cb for cb in self.__class__._after_failure_cbs if cb.matches(fs, ts)]

    def _match_after_guard_fail(
        self, fs: str | None, ts: str
    ) -> list[CallbackDefinition]:
        return [cb for cb in self.__class__._after_guard_fail_cbs if cb.matches(fs, ts)]

    async def _run_guards(self, from_state: str | None, to_state: str) -> None:
        for guard in self._match_guards(from_state, to_state):
            result = guard.func(self, self._model)
            result = await maybe_await(result)

            if not result:
                raise GuardFailedError(from_state, to_state)

    async def _run_before_cbs(self, fs, ts, record: TransitionRecord) -> None:
        for cb in self._match_before(fs, ts):
            await maybe_await(cb.func(self, self._model, record))

    async def _run_after_cbs(
        self, fs, ts, record: TransitionRecord, *, after_commit: bool
    ) -> None:
        for cb in self._match_after(fs, ts, after_commit=after_commit):
            await maybe_await(cb.func(self, self._model, record))

    async def _run_after_failure_cbs(self, fs, ts, exc: Exception) -> None:
        for cb in self._match_after_failure(fs, ts):
            await maybe_await(cb.func(self, self._model, exc))

    async def _run_after_guard_fail_cbs(self, fs, ts, exc: Exception) -> None:
        for cb in self._match_after_guard_fail(fs, ts):
            await maybe_await(cb.func(self, self._model, exc))
