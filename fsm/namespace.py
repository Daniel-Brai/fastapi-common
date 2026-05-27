from typing import Any

_DSL_KEYS: frozenset[str] = frozenset(
    ["state", "transition", "remove_state", "remove_transitions"]
)


class MachineNamespace(dict):
    """
    A dict subclass returned by ``StateMachineMeta.__prepare__``.

    When executed a ``StateMachine`` subclass body, it uses this object
    as the local namespace, so the DSL functions (``state``, ``transition``, …)
    are available as free names without any import.

    Inheritance is handled here: states and transitions from base classes are
    copied into ``_states`` / ``_transitions`` before the subclass body runs,
    so subclasses can extend or override parent machines.
    """

    def __init__(self, bases: tuple) -> None:
        super().__init__()

        self._states: dict[str, dict[Any, Any]] = {}
        self._transitions: list[dict[Any, Any]] = []

        for base in reversed(bases):
            if hasattr(base, "_states"):
                self._states.update(
                    {n: {"name": n, "initial": sd.initial}
                     for n, sd in base._states.items()}
                )
            if hasattr(base, "_transitions"):
                self._transitions.extend(
                    {"from": td.from_state, "to": list(td.to_states)}
                    for td in base._transitions
                )

        self["state"]              = self._add_state
        self["transition"]         = self._add_transition
        self["remove_state"]       = self._remove_state
        self["remove_transitions"] = self._remove_transitions


    def _add_state(self, name: str, *, initial: bool = False) -> None:
        """
        Declare a state.

        It is also creates an uppercase class constant so you can write something like ``OrderStateMachine.PENDING`` instead of the string ``"pending"``.
        """

        self._states[name] = {"name": name, "initial": initial}
        self[name.upper()] = name        

    def _add_transition(
        self,
        *,
        from_state: str,
        to: str | list[str],
    ) -> None:
        """
        Declare one or more valid target states from ``from_state``
        """

        if isinstance(to, str):
            to = [to]

        self._transitions.append({"from": from_state, "to": list(to)})

    def _remove_state(self, name: str) -> None:
        """
        Remove a state and every transition that references it

        Useful when extending a template machine and wanting to remove some of the inherited states
        """

        self._states.pop(name, None)
        self.pop(name.upper(), None) 

        cleaned: list[dict[str, Any]] = []

        for t in self._transitions:
            if t["from"] == name:
                continue

            new_to = [s for s in t["to"] if s != name]
            if new_to:
                cleaned.append({**t, "to": new_to})

        self._transitions = cleaned

    def _remove_transitions(
        self,
        *,
        from_state: str | None = None,
        to: str | None = None,
    ) -> None:
        """
        Remove specific transitions

        - Use ``from_state`` only remove *all* transitions from that state.
        - Use ``from_state`` and ``to`` to remove that specific edge.
        - Use ``to`` only  remove all transitions that include that target.
        """

        cleaned: list[dict[str, Any]] = []

        for t in self._transitions:
            from_match = from_state is None or t["from"] == from_state
            if from_match:
                if to is not None:
                    new_to = [s for s in t["to"] if s != to]

                    if not new_to:
                        # No more targets from this state, so remove the whole transition
                        continue

                    cleaned.append({**t, "to": new_to})
                else:
                    # Continue removing all transitions from this state
                    continue
            else:
                cleaned.append(t)

        self._transitions = cleaned

    def to_clean_dict(self) -> dict[str, Any]:
        """
        Retrieve a copy of this namespace with DSL function keys stripped out
        """

        return {k: v for k, v in self.items() if k not in _DSL_KEYS}