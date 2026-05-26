from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import PositiveInt
from sqlalchemy.orm import Session
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.audit.enums import AuditAction
from lib.audit.models.audit import Audit
from lib.audit.schemas import AuditPage

if TYPE_CHECKING:
    from lib.audit.mixins.audited import AuditedMixin


class AuditQuery:
    """
    Query builder for `Audit`.
    """

    def __init__(self, session: AsyncSession | Session):
        self._session = session
        self._filters: list[Any] = []
        self._order_asc: bool = False
        self._limit_n: int | None = None
        self._offset_n: int | None = None

    def for_model(self, model_class: type) -> "AuditQuery":
        """
        Filter to a specific model class.

        Example:

            AuditQuery(session).for_model(Post)
        """

        from lib.audit.mixins.audited import AuditedMixin

        if not issubclass(model_class, AuditedMixin):
            raise TypeError(
                f"{model_class.__name__} does not use AuditedMixin. " f"Only audited models can be queried."
            )

        type_string = model_class._audit_type_string()
        self._filters.append(Audit.auditable_type == type_string)
        return self

    def for_model_id(self, model_class: type, pk: Any) -> "AuditQuery":
        """
        Filter to a specific model instance by primary key.

            AuditQuery(session).for_model_id(Post, 42)
        """

        self.for_model(model_class)
        self._filters.append(col(Audit.auditable_id) == str(pk))
        return self

    def for_model_instance(self, instance: "AuditedMixin") -> "AuditQuery":
        """
        Filter to a specific model instance.

            AuditQuery(session).for_model_instance(post)
        """

        from lib.audit.models.audit import Audit

        self._filters.append(col(Audit.auditable_type) == instance._audit_type_string())
        self._filters.append(col(Audit.auditable_id) == instance._audit_id_string())
        return self

    def by_action(self, *actions: Literal["create", "update", "destroy"]) -> "AuditQuery":
        """
        Filter by action(s).

            .by_action("update")
            .by_action("create", "update")
        """

        if len(actions) == 1:
            self._filters.append(col(Audit.action) == AuditAction(actions[0]))
        else:
            self._filters.append(col(Audit.action).in_([AuditAction(action) for action in actions]))

        return self

    def by_auditor(self, auditor: Any) -> "AuditQuery":
        """
        Filter to changes made by a specific auditor (user model instance).

            .by_auditor(user)
        """

        auditor_type = type(auditor).__name__
        auditor_id = str(getattr(auditor, "id", auditor))

        self._filters.append(Audit.auditor_type == auditor_type)
        self._filters.append(Audit.auditor_id == auditor_id)
        return self

    def by_auditor_type(self, auditor_type: str) -> "AuditQuery":
        """
        Filter by auditor class name, e.g. .by_auditor_type('AdminUser').

        Example:
            by_auditor_type("User")  # all changes made by any User, regardless of ID
        """

        self._filters.append(col(Audit.auditor_type == auditor_type))

        return self

    def by_request(self, request_id: str) -> "AuditQuery":
        """
        Filter to all changes in a single HTTP request.

        Example:

            # to get all audits with request_id "abc123".
            .by_request("abc123")
        """

        self._filters.append(col(Audit.request_id == request_id))
        return self

    def since(self, dt: datetime) -> "AuditQuery":
        """
        Include only records created at or after dt.

        Example:
            # all audits in 2025
            .since(datetime(2025, 1, 1))
            .until(datetime(2026, 1, 1))
        """

        self._filters.append(col(Audit.created_at) >= dt)
        return self

    def until(self, dt: datetime) -> "AuditQuery":
        """
        Include only records created at or before dt.

        Example:

            # all audits in 2025
            .since(datetime(2025, 1, 1))
            .until(datetime(2026, 1, 1))
        """

        self._filters.append(col(Audit.created_at) <= dt)
        return self

    def with_comment(self) -> "AuditQuery":
        """
        Include only records that have a non-null comment.
        """

        self._filters.append(col(Audit.comment).isnot(None))
        return self

    def order_asc(self) -> "AuditQuery":
        """
        Order by created_at ascending (oldest first). Default is newest first.
        """

        self._order_asc = True
        return self

    def limit(self, n: int) -> "AuditQuery":
        """
        Limit result count.
        """
        self._limit_n = n
        return self

    def offset(self, n: int) -> "AuditQuery":
        """
        Skip n rows.
        """
        self._offset_n = n
        return self

    def _build_stmt(self):

        stmt = select(Audit)
        for f in self._filters:
            stmt = stmt.where(f)

        if self._order_asc:
            stmt = stmt.order_by(col(Audit.created_at).asc())
        else:
            stmt = stmt.order_by(col(Audit.created_at).desc())

        if self._offset_n is not None:
            stmt = stmt.offset(self._offset_n)

        if self._limit_n is not None:
            stmt = stmt.limit(self._limit_n)

        return stmt

    async def _execute(self, stmt):
        if isinstance(self._session, AsyncSession):
            return await self._session.exec(stmt)

        return self._session.execute(stmt)

    async def all(self) -> list["Audit"]:
        """
        Execute and return all matching records.
        """
        result = await self._execute(self._build_stmt())

        return list(result.scalars().all())

    async def first(self) -> Audit | None:
        """
        Execute and return the first matching record or None.
        """
        result = await self._execute(self._build_stmt())
        return result.scalars().first()

    async def count(self) -> int:
        """
        Return the count of matching records.
        """

        count_stmt = select(func.count()).select_from(Audit)
        for f in self._filters:
            count_stmt = count_stmt.where(f)

        result = await self._execute(count_stmt)
        return int(result.scalar_one())

    async def page(self, page: PositiveInt = 1, per_page: int = 25) -> AuditPage:
        """
        Paginate results.

        Returns an AuditPage dataclass with:
            records    list[Audit]
            page       current page (1-indexed)
            per_page   page size
            total      total count
            pages      total page count

            AuditQuery(session).for_model(Post).page(page=2, per_page=25)
        """

        total = await self.count()
        pages = max(1, (total + per_page - 1) // per_page)

        self._limit_n = per_page
        self._offset_n = (page - 1) * per_page

        return AuditPage(
            records=await self.all(),
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
        )
