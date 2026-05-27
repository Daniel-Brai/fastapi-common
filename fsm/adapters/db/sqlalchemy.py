import json
from datetime import datetime
from typing import Any

from ...types import TransitionRecord
from ...exceptions import TransitionConflictError

from ..base import AbstractAdapter


try:
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fsm.adapters.sqlalchemy requires SQLAlchemy 2.x. "
        "Install it with: pip install sqlalchemy"
    ) from exc



class SQLAlchemyTransitionMixin:
    """
    Column definitions required by the SQLAlchemy adapter.

    Attributes:
        from_state (str | None): The name of the state from which the transition originates.
        to_state (str): The name of the state to which the transition goes.
        sort_key (int): An integer used to order transitions chronologically.
        metadata_ (str): A JSON-encoded string storing additional metadata about the transition.
        created_at (datetime): The timestamp when the transition was created.
        most_recent (bool): A flag indicating if this transition is the most recent one for its owner.

    
    Usage
    -----

    Mix this into your ORM transition model::

        class OrderTransition(SQLAlchemyTransitionMixin, Base):
            __tablename__ = "order_transitions"
            id          = Column(Integer, primary_key=True)
            order_id    = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)

    Or with SQLModel::

        class OrderTransition(SQLAlchemyTransitionMixin, SQLModel, table=True):
            __tablename__ = "order_transitions"
            id: int | None = Field(default=None, primary_key=True)
            order_id: int  = Field(foreign_key="order.id")

    """

    from_state: str | None
    to_state: str
    sort_key: int
    metadata_: str  
    created_at: datetime
    most_recent: bool 

    @classmethod
    def _columns(cls):
        return frozenset(
            [
                "from_state",
                "to_state",
                "sort_key",
                "metadata_",
                "created_at",
                "most_recent",
            ]
        )


def make_transition_table(base, table_name: str, foreign_key: str):
    """
    Factory that generates a ready-to-use SQLAlchemy transition model

    Useful when you do not want to write the model by hand::

        Base = declarative_base()
        OrderTransition = make_transition_table(Base, "order_transitions", "orders.id")

    Parameters
    ----------
    base:
        Your ``declarative_base()`` instance.
    table_name:
        Name of the DB table, e.g. ``"order_transitions"``.
    foreign_key:
        SQLAlchemy FK string, e.g. ``"orders.id"``.
    """

    from sqlalchemy import (
        Boolean,
        Column,
        DateTime,
        ForeignKey,
        Integer,
        String,
        UniqueConstraint,
    )

    class _Transition(SQLAlchemyTransitionMixin, base):  # type: ignore[valid-type]
        __tablename__ = table_name
        __table_args__ = (
            UniqueConstraint("owner_id", "sort_key", name=f"uq_{table_name}_sort_key"),
        )

        id = Column(Integer, primary_key=True, autoincrement=True)
        owner_id = Column(Integer, ForeignKey(foreign_key), nullable=False, index=True)
        from_state = Column(String(64), nullable=True)  # type: ignore[assignment]
        to_state = Column(String(64), nullable=False)  # type: ignore[assignment]
        sort_key = Column(Integer, nullable=False, default=0)  # type: ignore[assignment]
        metadata_ = Column(String, nullable=False, default="{}")  # type: ignore[assignment]
        created_at = Column(DateTime, nullable=False, default=datetime.now)  # type: ignore[assignment]
        most_recent = Column(Boolean, nullable=False, default=False)  # type: ignore[assignment]

    _Transition.__name__ = table_name.replace("_", " ").title().replace(" ", "")
    return _Transition


class SQLAlchemyAdapter(AbstractAdapter):
    """
    Async SQLAlchemy adapter.

    Parameters
    ----------
    session:
        An ``AsyncSession`` instance.
    model:
        The parent model object (e.g. an ``Order``).
    transition_class:
        The ORM class used to persist transitions.
    foreign_key_attr:
        Name of the attribute on ``transition_class`` that holds the FK
        pointing to ``model``'s primary key.  Defaults to ``"owner_id"``.
    owner_id_attr:
        Name of the attribute on ``model`` that holds the primary key used
        by the FK above.  Defaults to ``"id"``.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        model: Any,
        transition_class: type,
        foreign_key_attr: str = "owner_id",
        owner_id_attr: str = "id",
    ) -> None:
        self._session = session
        self._model = model
        self._cls = transition_class
        self._fk_attr = foreign_key_attr
        self._owner_id_attr = owner_id_attr
        self._cache: list[TransitionRecord] | None = None

    def _owner_id(self) -> Any:
        return getattr(self._model, self._owner_id_attr)

    def _fk_filter(self):
        return getattr(self._cls, self._fk_attr) == self._owner_id()

    def _orm_to_record(self, row: Any) -> TransitionRecord:
        try:
            meta = json.loads(row.metadata_) if row.metadata_ else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}

        return TransitionRecord(
            id=row.id,
            from_state=row.from_state,
            to_state=row.to_state,
            metadata=meta,
            sort_key=row.sort_key,
            created_at=row.created_at,
        )

    async def history(self) -> list[TransitionRecord]:
        if self._cache is not None:
            return self._cache

        stmt = select(self._cls).where(self._fk_filter()).order_by(self._cls.sort_key)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        records = [self._orm_to_record(r) for r in rows]

        self._cache = records
        return records

    async def last_transition(
        self, *, force_reload: bool = False
    ) -> TransitionRecord | None:
        if force_reload:
            self._cache = None

        h = await self.history()

        return h[-1] if h else None

    async def create_transition(self, record: TransitionRecord) -> TransitionRecord:
        # Reset most_recent on previous transitions
        prev_stmt = select(self._cls).where(
            self._fk_filter(), self._cls.most_recent.is_(True)
        )

        prev_result = await self._session.execute(prev_stmt)
        for prev in prev_result.scalars().all():
            prev.most_recent = False

        orm_obj = self._cls(
            **{
                self._fk_attr: self._owner_id(),
                "from_state": record.from_state,
                "to_state": record.to_state,
                "sort_key": record.sort_key,
                "metadata_": json.dumps(record.metadata),
                "created_at": record.created_at,
                "most_recent": True,
            }
        )

        self._session.add(orm_obj)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise TransitionConflictError(
                f"DB conflict persisting transition to '{record.to_state}'"
            ) from exc

        saved = self._orm_to_record(orm_obj)
        # Invalidate cache so next call re-reads from DB
        self._cache = None
        return saved
