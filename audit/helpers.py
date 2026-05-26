from typing import Any

from lib.audit.context import get_comment, get_remote_addr, get_request_id
from lib.audit.enums import AuditAction
from lib.audit.mixins import AuditedMixin
from lib.audit.models import Audit


def _auditor_fields() -> tuple[str | None, str | None]:
    from lib.audit.registry import audit_registry

    if not audit_registry.is_configured:
        return None, None

    if (
        audit_registry.auditor_loader is None
        or audit_registry.auditor_type_fn is None
        or audit_registry.auditor_id_fn is None
    ):
        return None, None

    auditor = audit_registry.auditor_loader()
    if auditor is None:
        return None, None
    try:
        return (
            audit_registry.auditor_type_fn(auditor),
            audit_registry.auditor_id_fn(auditor),
        )
    except Exception:
        return None, None


def _serialise(value: Any) -> Any:
    from lib.audit.registry import audit_registry

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if audit_registry.serialiser is None:
        return str(value)

    return audit_registry.serialiser(value)


def _tracked_columns(instance: Any) -> set[str]:
    from lib.audit.registry import audit_registry

    return instance._audit_tracked_columns() - audit_registry.excluded_columns


def _build_update_record(instance: Any) -> Any | None:
    from sqlalchemy.orm.attributes import get_history

    from lib.audit.context import get_comment, get_remote_addr, get_request_id

    tracked = _tracked_columns(instance)
    changes: dict[str, Any] = {}

    for col_name in tracked:
        hist = get_history(instance, col_name)
        if hist.deleted:
            old = _serialise(hist.deleted[0])
            new = _serialise(hist.added[0] if hist.added else None)
            if old != new:
                changes[col_name] = {"old": old, "new": new}

    if not changes:
        return None

    auditor_type, auditor_id = _auditor_fields()
    return Audit(  # type: ignore[call-arg]
        auditable_type=instance._audit_type_string(),
        auditable_id=instance._audit_id_string(),
        action=AuditAction.UPDATE,
        audited_changes=changes,
        auditor_type=auditor_type,
        auditor_id=auditor_id,
        comment=get_comment(),
        request_id=get_request_id(),
        remote_address=get_remote_addr(),
    )


def _build_destroy_record(instance: Any) -> Any | None:
    tracked = _tracked_columns(instance)
    changes = {col: _serialise(getattr(instance, col, None)) for col in tracked}
    if not changes:
        return None

    auditor_type, auditor_id = _auditor_fields()
    return Audit(  # type: ignore[call-arg]
        auditable_type=instance._audit_type_string(),
        auditable_id=instance._audit_id_string(),
        action=AuditAction.DESTROY,
        audited_changes=changes,
        auditor_type=auditor_type,
        auditor_id=auditor_id,
        comment=get_comment(),
        request_id=get_request_id(),
        remote_address=get_remote_addr(),
    )


def default_serialiser(value: Any) -> Any:
    import datetime
    import decimal
    import enum
    import uuid

    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        return value.model_dump()

    if isinstance(value, (list, tuple)):
        return [_serialise(v) for v in value]

    if isinstance(value, dict):
        return {k: _serialise(v) for k, v in value.items()}

    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()

    if isinstance(value, decimal.Decimal):
        return float(value)

    if isinstance(value, int | str | bool | None):
        return value

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, enum.Enum):
        return value.value

    # if it is a class, serialize to dict
    if isinstance(value, type):
        return {k: _serialise(v) for k, v in vars(value).items() if not k.startswith("__")}

    return str(value)


def before_flush(session: Any, flush_context: Any, instances: Any) -> None:  # noqa: ARG001
    """
    Phase 1 of 2.

    - Updates: diff captured here while SQLAlchemy history is still live.
    - Deletes: snapshot captured here while the row is still in memory.
    - Inserts: context + non-PK values snapshotted and queued; PKs not yet
      assigned (autoincrement happens during the flush).
    """

    from lib.audit.registry import audit_registry

    if not audit_registry.is_configured:
        return

    for instance in list(session.dirty):
        if isinstance(instance, AuditedMixin) and not isinstance(instance, Audit):
            if "update" in instance._audit_on_set():
                rec = _build_update_record(instance)
                if rec:
                    session.add(rec)

    for instance in list(session.deleted):
        if isinstance(instance, AuditedMixin) and not isinstance(instance, Audit):
            if "destroy" in instance._audit_on_set():
                rec = _build_destroy_record(instance)
                if rec:
                    session.add(rec)

    # Queue inserts and  write them in after_flush once PKs are assigned.
    pending = []
    for instance in list(session.new):
        if isinstance(instance, AuditedMixin) and not isinstance(instance, Audit):
            if "create" in instance._audit_on_set():
                tracked = _tracked_columns(instance)
                changes = {col: _serialise(getattr(instance, col, None)) for col in tracked}
                if changes:
                    auditor_type, auditor_id = _auditor_fields()
                    pending.append(
                        {
                            "instance": instance,
                            "changes": changes,
                            "auditor_type": auditor_type,
                            "auditor_id": auditor_id,
                            "comment": get_comment(),
                            "request_id": get_request_id(),
                            "remote_addr": get_remote_addr(),
                        }
                    )

    if pending:
        audit_registry._pending_creates[id(session)] = pending


def after_flush(session: Any, flush_context: Any) -> None:  # noqa: ARG001
    """
    Phase 2 of 2.

    Write queued INSERT audit records now that autoincrement PKs are assigned.
    Pops from registry._pending_creates — no module-level state involved.
    """

    from lib.audit.registry import audit_registry

    pending = audit_registry._pending_creates.pop(id(session), None)
    if not pending or not audit_registry.is_configured:
        return

    for item in pending:
        instance = item["instance"]
        audit = Audit(  # type: ignore[call-arg]
            auditable_type=instance._audit_type_string(),
            auditable_id=instance._audit_id_string(),
            action=AuditAction.CREATE,
            audited_changes=item["changes"],
            auditor_type=item["auditor_type"],
            auditor_id=item["auditor_id"],
            comment=item["comment"],
            request_id=item["request_id"],
            remote_address=item["remote_addr"],
        )

        session.add(audit)
