from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import TIMESTAMP, VARCHAR, Column, Field, SQLModel

from lib.audit.enums import AuditAction


class Audit(SQLModel, table=True):
    """
    Represent a model that stores every tracked change on audited models.  Each change creates one Audit record with the details of what changed, who changed it, and when.

    Attributes:

        id (int): primary key of the audit record.
        action (AuditAction): the type of change
        auditable_type (str): fully-qualified class name of the audited model, e.g. "app.models.post.Post"
        auditable_id (str): the audited model's primary key, serialised to string for
                            compatibility with int, UUID, and composite keys.
        audited_changes (dict): a JSONB column storing the change details.  The format depends
                            on the action type but generally includes the old and new values of changed fields.
        auditor_type (str | None): class name of the auditor model, e.g. "User".  None for system or background changes.
        auditor_id (str | None): auditor's primary key serialised to string.  None for system or background changes.
        comment (str | None): freeform note which is set via audit_comment() context manager or dependency.
        remote_address (str | None): client IP address (populated by AuditMiddleware).
        request_uuid (str | None): correlation ID (e.g. from X-Request-ID header) that ties all audits in one request together.
        created_at (datetime): timestamp of when the change occurred.

    Changes format:

        create:  {"field": <new_value>, ...}
                            All non-excluded column values at creation time.

        update:  {"field": {"old": <old_value>, "new": <new_value>}, ...}
                            Only the fields that changed.

        destroy: {"field": <last_value>, ...}
                            All non-excluded column values just before deletion.

    Querying:

        from lib.audit.models import Audit

        # All audits for a specific Post instance
        Post.audit_trail(session)               # instance method via AuditedMixin

        # Fluent query builder
        from lib.audit.query import AuditQuery

        records = (
                AuditQuery(session)
                .for_model(Post)
                .by_action("update")
                .by_auditor(current_user)
                .since(datetime(2025, 1, 1))
                .all()
        )
    """

    __tablename__ = "audit_records"  # type: ignore[assignment]

    id: int = Field(index=True, primary_key=True)

    # Fully-qualified class name: "app.models.post.Post"
    auditable_type: str = Field(index=True)

    # The model's primary key serialised to string.
    # String so it works with int, UUID, or composite PKs.
    auditable_id: str = Field(index=True)

    action: AuditAction = Field(sa_column=Column(VARCHAR(20), nullable=False, index=True))

    # Serialised change dict
    audited_changes: dict[Any, Any] = Field(sa_column=Column(JSONB(), nullable=False, default=dict))

    # Class name of the auditor model, e.g. "User"
    auditor_type: str | None = Field(default=None, index=True)

    # Auditor's PK serialised to string.  None for system/background changes.
    auditor_id: str | None = Field(default=None, index=True)

    # Freeform note  which is set via audit_comment() context manager or dependency.
    comment: str | None = Field(default=None)

    # Client IP address (populated by AuditMiddleware).
    remote_address: str | None = Field(default=None)

    # Correlation ID mainly in the X-Request-ID header tied to the HTTP request that  lets you group all audits in one request.
    request_id: str | None = Field(default=None, index=True)

    created_at: datetime = Field(
        sa_column=Column(TIMESTAMP(timezone=True), default=datetime.now, nullable=False, index=True)
    )

    @property
    def auditor_label(self) -> str:
        """
        Human-readable label for the auditor: 'User#42' or 'system'.
        """
        if self.auditor_type and self.auditor_id:
            return f"{self.auditor_type}#{self.auditor_id}"

        return "system"

    @property
    def auditable_label(self) -> str:
        """
        Human-readable label for the auditable object: 'Post#7'.
        """

        short_type = self.auditable_type.rsplit(".", 1)[-1]
        return f"{short_type}#{self.auditable_id}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditRecord #{self.id} " f"{self.action} {self.auditable_label} " f"by {self.auditor_label}>"
