from typing import Callable

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from lib.audit.registry import AuditRegistry, audit_registry


def configure_audit(
    engine: AsyncEngine | Engine,
    *,
    auditor_loader: Callable | None = None,
    auditor_id_fn: Callable | None = None,
    auditor_type_fn: Callable | None = None,
    excluded_columns: list[str] | None = None,
    serialiser: Callable | None = None,
    rentention_days: int | None = None,
) -> AuditRegistry:
    """
    Configure the audit library's global settings and wire up SQLAlchemy session listeners.

    This function should be called once during application startup. It acts as a module-level shortcut
    that delegates to ``audit_registry.configure_audit()``.

    Parameters
    ----------
    engine
        SQLAlchemy Engine or AsyncEngine. Used by background jobs (like SweepAuditJob) to open sessions.
    auditor_loader
        Callable() -> user | None. Resolves the current user. Defaults to `audit.context.get_auditor`.
    auditor_id_fn
        Callable(user) -> str. Extracts the user ID. Defaults to `str(user.id)`.
    auditor_type_fn
        Callable(user) -> str. Extracts the user type. Defaults to `type(user).__name__`.
    excluded_columns
        List of column names statically and globally excluded from all models' audit records.
    serialiser
        Callable(value) -> JSON-safe value. Used for custom JSON serialization.
    rentention_days
        Number of days to retain audit records. Defaults to None.

    Usage
    -----
    ```python
    from lib.audit import configure_audit

    configure_audit(
        engine=db.engine,
        excluded_columns=["password_hash", "secret_token"],
    )
    ```
    """
    return audit_registry.configure_audit(
        engine,
        auditor_loader=auditor_loader,
        auditor_id_fn=auditor_id_fn,
        auditor_type_fn=auditor_type_fn,
        excluded_columns=excluded_columns,
        serialiser=serialiser,
        rentention_days=rentention_days,
    )


def get_registry() -> AuditRegistry:
    """
    Return the singleton.  Raises if configure_audit() has not been called.
    """
    audit_registry.assert_configured()

    return audit_registry


def get_rentention_days() -> int:
    """
    Return the number of days audit records are retained for, as configured in the registry.
    """
    return get_registry().rentention_days
