from typing import Any, Literal

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.audit.enums import AuditAction
from lib.audit.schemas import AuditVersion
from lib.logger import get_logger

logger = get_logger("lib.audit.mixins")


_DEFAULT_AUDIT_ON = ("create", "update", "destroy")


class AuditedMixin:
    """
    Mixin to add to SQLAlchemy/SQLModel models for automatic auditing of create/update/destroy actions.

    SQLModel usage:

        from audit import AuditedMixin

        class Post(AuditedMixin, SQLModel, table=True):
            __tablename__ = "posts"

            id: int | None = Field(default=None, primary_key=True)
            title: str
            content: str
            draft: bool = Field(default=True)

            # Exclude sensitive or noisy fields from audit records:
            __audit_exclude__ = ["draft"]

            # OR: audit only specific fields:
            # __audit_only__ = ["title", "content"]

            # OR: restrict which actions are tracked:
            # __audit_on__ = ["create", "update"]   # skip "destroy"

    SQLAlchemy declarative usage:

        from audit import AuditedMixin
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        class Base(DeclarativeBase):
            pass

        class Post(AuditedMixin, Base):
            __tablename__ = "posts"
            id: Mapped[int] = mapped_column(primary_key=True)
            title: Mapped[str]

    Class-level configuration:

        __audit_exclude__  list[str]   Fields never recorded in audit changes.
                                        Defaults to [] (include everything).
                                        Tip: exclude passwords, salts, tokens.

        __audit_only__     list[str]   If set, ONLY these fields are recorded.
                                        Mutually exclusive with __audit_exclude__.

        __audit_on__       list[str]   Which actions to track.
                                        Default: ["create", "update", "destroy"]

    Instance methods:

        instance.audit_trail(session) -> list[Audit]
            All audit records for this instance, newest first.

        instance.audits(session) -> AuditQuery
            Fluent query builder pre-filtered to this instance.

        instance.audit_versions(session) -> list[AuditVersion]
            Reconstruct the full state at each version (creates + updates applied).

    Add to a model class to register it for auditing when configure_audit()
    is called.

    All tracking is driven by SQLAlchemy session events, so no manual instrumentation is needed at call sites.
    """

    #: Fields to exclude from audit records (list of column names).
    __audit_exclude__: list[str] = []

    #: If set, ONLY these fields are recorded.  Takes priority over __audit_exclude__.
    __audit_only__: list[str] = []

    #: Which actions to track.
    __audit_on__: list[Literal["create", "update", "destroy"]] = list(_DEFAULT_AUDIT_ON)

    @classmethod
    def _audit_tracked_columns(cls) -> set[str]:
        """
        Return the set of column names that should appear in audit records.
        Respects __audit_only__ and __audit_exclude__.

        Primary key columns are always excluded — they are already captured in
        auditable_id and would show as None in create records (since autoincrement
        PKs are not assigned until after the flush).
        """
        try:
            mapper: Any = sa_inspect(cls)

            if mapper is None:
                raise ValueError("Could not inspect mapper for class %s", cls)

        except Exception as e:
            logger.error("AuditedMixin: Error occurred while inspecting mapper: %s", e)
            return set()

        pk_cols = {prop.key for prop in mapper.column_attrs if prop.columns[0].primary_key}

        all_cols = {c.key for c in mapper.columns} - pk_cols

        if cls.__audit_only__:
            return all_cols & set(cls.__audit_only__)

        excluded = set(cls.__audit_exclude__)
        return all_cols - excluded

    @classmethod
    def _audit_on_set(cls) -> frozenset[str]:
        return frozenset(cls.__audit_on__)

    @classmethod
    def _audit_type_string(cls) -> str:
        """
        Fully-qualified class name for storage in auditable_type.
        """
        return f"{cls.__module__}.{cls.__qualname__}"

    def _audit_id_string(self) -> str:
        """
        Serialise the primary key to string for auditable_id.
        """
        try:
            mapper: Any = sa_inspect(self)

            if mapper is None:
                raise ValueError("Could not inspect mapper for instance of type %s", type(self))

        except Exception as e:
            logger.error("AuditedMixin: Error occurred while inspecting mapper: %s", e)
            return str(getattr(self, "id", "unknown"))

        pk_cols = mapper.primary_key

        if len(pk_cols) == 1:
            return str(getattr(self, pk_cols[0].name))

        # Composite PK: "1,abc"
        return ",".join(str(getattr(self, c.name)) for c in pk_cols)

    def audit_trail(self, session) -> list:
        """
        Return all Audit rows for this instance, newest first.

            post.audit_trail(session)
        """

        from sqlmodel import col, select

        from lib.audit.models.audit import Audit

        stmt = (
            select(Audit)
            .where(Audit.auditable_type == self._audit_type_string())
            .where(Audit.auditable_id == self._audit_id_string())
            .order_by(col(Audit.created_at).desc())
        )
        return session.exec(stmt).all()

    async def audits(self, session: AsyncSession | Session):
        """
        Return a pre-filtered AuditQuery for this instance.

            post.audits(session).by_action("update").all()
        """

        from lib.audit.query import AuditQuery

        return AuditQuery(session).for_model_instance(self)

    async def audit_versions(self, session: AsyncSession | Session) -> list[AuditVersion]:
        """
        Reconstruct the full state of this object at each version.

        Applies create and update records in chronological order and returns
        a list of `AuditVersion` snapshots. The first entry is the creation
        state; each subsequent entry is the state after an update.


        Example:

            for version in await post.audit_versions(session):
                print(version.state["title"], version.audit_action, version.audit_at)
        """

        from sqlmodel import col, select

        from lib.audit.models.audit import Audit

        stmt = (
            select(Audit)
            .where(col(Audit.auditable_type) == self._audit_type_string())
            .where(col(Audit.auditable_id) == self._audit_id_string())
            .where(col(Audit.action).in_([AuditAction.CREATE, AuditAction.UPDATE]))
            .order_by(col(Audit.created_at).asc())
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)

        records = result.scalars().all()

        state: dict[str, Any] = {}
        versions: list[AuditVersion] = []

        for rec in records:
            if rec.action == AuditAction.CREATE:
                state = dict(rec.audited_changes)
            elif rec.action == AuditAction.UPDATE:
                for field, change in rec.audited_changes.items():
                    if isinstance(change, dict) and "new" in change:
                        state[field] = change["new"]
                    else:
                        state[field] = change

            versions.append(
                AuditVersion(
                    state=dict(state),
                    audit_id=rec.id,
                    audit_action=rec.action,
                    audit_at=rec.created_at,
                    audit_by=rec.auditor_label,
                    audit_comment=rec.comment,
                )
            )

        return versions
