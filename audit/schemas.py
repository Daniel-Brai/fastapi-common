from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
    from lib.audit.models.audit import Audit


@dataclass(slots=True)
class AuditVersion:
    """
    Represents one reconstructed version snapshot of an audited object.

    Attributes:
        state (dict): the full state of the object at this version.
        audit_id (Any): the ID of the corresponding Audit record, if available.
        audit_action (str): the action type ("create" or "update") of the corresponding
        audit_at (datetime): the timestamp of the audit event.
        audit_by (str): the user who performed the audit event.
        audit_comment (str | None): a comment associated with the audit event.
        audit_by (str): a human-readable label for the auditor, e.g. "User#123" or "System".
        audit_comment (str | None): the comment from the audit record, if any.
    """

    state: dict[str, Any]
    audit_id: Any
    audit_action: str
    audit_at: datetime
    audit_by: str
    audit_comment: str | None


@dataclass(slots=True)
class AuditPage:
    """
    Paginated audit query result.
    """

    records: list["Audit"]
    page: int
    per_page: int
    total: int
    pages: int
