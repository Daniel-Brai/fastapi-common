from datetime import UTC, datetime
import json
from typing import Any, Optional


from ..base import AbstractAdapter
from ...types import TransitionRecord
from ...exceptions import TransitionConflictError

try:
    from sqlmodel import Field, SQLModel, select, col
    from sqlalchemy.exc import IntegrityError
    from sqlmodel.ext.asyncio.session import AsyncSession
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "fsm.adapters.sqlmodel requires sqlmodel. "
        "Install it with: pip install sqlmodel"
    ) from exc


class SQLModelTransitionBase(SQLModel):
    """
    A non-table base class providing all the fields FSM needs.

    Inherit from this *and* set ``table=True`` in your concrete class.
    You must still add:

    - A primary key field (``id``).
    - A foreign key field pointing to the parent model.
    - Optionally a ``Relationship`` back-reference.

    Example::

        class OrderTransition(SQLModelTransitionBase, table=True):
            __tablename__ = "order_transitions"
            id:       int | None = Field(default=None, primary_key=True)
            order_id: int        = Field(foreign_key="order.id", index=True)
    """

    from_state: Optional[str] = Field(default=None, max_length=500)
    to_state: str = Field(max_length=500)
    sort_key: int = Field(default=0, index=True)
    metadata_: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    most_recent: bool = Field(default=False, index=True)


class SQLModelAdapter(AbstractAdapter):
    """
    Async SQLModel adapter.

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
        return col(getattr(self._cls, self._fk_attr)) == self._owner_id()

    def _orm_to_record(self, row: Any) -> TransitionRecord:
        try:
            meta = (
                json.loads(row.metadata_)
                if row.metadata_ and isinstance(row.metadata_, str)
                else (row.metadata_ if isinstance(row.metadata_, dict) else {})
            )
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
        result = await self._session.exec(stmt)
        rows = result.all()
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
        prev_stmt = select(self._cls).where(
            self._fk_filter(), col(self._cls.most_recent).is_(True)
        )

        prev_result = await self._session.exec(prev_stmt)
        for prev in prev_result.all():
            prev.most_recent = False

        orm_obj = self._cls(
            **{
                self._fk_attr: self._owner_id(),
                "from_state": record.from_state,
                "to_state": record.to_state,
                "sort_key": record.sort_key,
                "metadata_": record.metadata,
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
        self._cache = None
        return saved
