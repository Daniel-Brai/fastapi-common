from ..types import TransitionRecord
from .base import AbstractAdapter


class MemoryAdapter(AbstractAdapter):
    """
    In-memory adapter for storing transition records. 
    
    This adapter is not persistent and is intended for testing or temporary use cases.
    """

    def __init__(self) -> None:
        self._history: list[TransitionRecord] = []

    async def history(self) -> list[TransitionRecord]:
        return list(self._history)

    async def last_transition(self, *, force_reload: bool = False) -> TransitionRecord | None:
        return self._history[-1] if self._history else None

    async def create_transition(self, record: TransitionRecord) -> TransitionRecord:
        self._history.append(record)
        return record