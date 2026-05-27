from abc import ABC, abstractmethod

from ..types import TransitionRecord


class AbstractAdapter(ABC):
    """
    Abstract base class for FSM adapters. 
    """
   
    @abstractmethod
    async def history(self) -> list[TransitionRecord]:
        raise NotImplementedError("Subclasses must implement the `history` method")

    @abstractmethod
    async def last_transition(self, *, force_reload: bool = False) -> TransitionRecord | None:
        raise NotImplementedError("Subclasses must implement the `last_transition` method")
    
    @abstractmethod
    async def create_transition(self, record: TransitionRecord) -> TransitionRecord:
        raise NotImplementedError("Subclasses must implement the `create_transition` method")