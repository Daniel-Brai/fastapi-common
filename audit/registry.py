from typing import Any, Callable

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from lib.audit.context import get_auditor as _default_loader
from lib.audit.exceptions import AuditNotConfigured
from lib.audit.helpers import default_serialiser
from lib.logger import get_logger

logger = get_logger("lib.audit.registry")


_DEFAULT_AUDIT_RENTENTION_DAYS = 30


class AuditRegistry:
    """
    Registry for audit configuration and state.
    """

    def __init__(self) -> None:
        self._configured: bool = False
        self.engine: AsyncEngine | Engine | None = None
        self.auditor_loader: Callable | None = None
        self.auditor_id_fn: Callable | None = None
        self.auditor_type_fn: Callable | None = None
        self.excluded_columns: frozenset[str] = frozenset()
        self.serialiser: Callable | None = None
        self.rentention_days: int = _DEFAULT_AUDIT_RENTENTION_DAYS

        # Whether SQLAlchemy session event listeners have been registered.
        # Stored on the registry rather than a module global so this state
        # is encapsulated alongside all other registry state.
        self._listeners_wired: bool = False

        # Per-flush staging area: id(session) → list of pending create dicts.
        # Populated in before_flush, consumed and cleared in after_flush.
        # In-memory is correct because:
        #   • sessions are process-local objects
        #   • one flush per session at a time (no id collision between concurrent flushes)
        #   • data lives for microseconds
        self._pending_creates: dict[int, list] = {}

    def configure_audit(
        self,
        engine: Any = None,
        *,
        auditor_loader: Callable | None = None,
        auditor_id_fn: Callable | None = None,
        auditor_type_fn: Callable | None = None,
        excluded_columns: list[str] | None = None,
        serialiser: Callable | None = None,
        rentention_days: int | None = None,
    ) -> "AuditRegistry":
        """
        Set configuration and wire the SQLAlchemy session listeners.

        Safe to call multiple times — re-configuring updates settings without
        duplicating event listeners (_listeners_wired prevents double-registration).

        Parameters
        ----------
        engine
            SQLAlchemy Engine or AsyncEngine.  Optional — the flush listeners
            write to whatever session is already open and do not need the engine.
            Only SweepAuditJob uses this to open its own session.
        auditor_loader
            Callable() → user | None.  Default: audit.context.get_auditor.
        auditor_id_fn
            Callable(user) → str.  Default: lambda u: str(u.id).
        auditor_type_fn
            Callable(user) → str.  Default: lambda u: type(u).__name__.
        excluded_columns
            Column names globally excluded from all models' audit records.
            Per-model __audit_exclude__ is merged with this at write time.
        serialiser
            Callable(value) → JSON-safe value.

        Returns
        -------
        self  — the singleton, for chaining.
        """

        self.engine = engine
        self.auditor_loader = auditor_loader or _default_loader
        self.auditor_id_fn = auditor_id_fn or (lambda u: str(getattr(u, "id", u)))
        self.auditor_type_fn = auditor_type_fn or (lambda u: type(u).__name__)
        self.excluded_columns = frozenset(excluded_columns or [])
        self.serialiser = serialiser or default_serialiser
        self.rentention_days = rentention_days or self.rentention_days
        self._configured = True

        # Wire listeners once: the _listeners_wired flag on the registry
        # (not a module global) prevents double-registration on reconfigure.
        self._wire_listeners()

        logger.info("Audit: configured  %r", self)
        return self

    @property
    def is_configured(self) -> bool:
        """
        True after configure_audit() has been called at least once.
        """
        return self._configured

    def assert_configured(self) -> None:
        if not self._configured:
            raise AuditNotConfigured()

    def __repr__(self) -> str:  # pragma: no cover
        if not self._configured:
            return "AuditRegistry(unconfigured)"

        engine_name = type(self.engine).__name__ if self.engine else "None"

        return f"AuditRegistry(engine={engine_name})"

    def get_sync_engine(self) -> Engine | None:
        """
        Return the sync engine for use in synchronous DB operations.

        AsyncEngine wraps a sync Engine and exposes it via .sync_engine.
        Sync Engine is returned as-is.  This is the only place where
        AsyncEngine / Engine divergence is handled.

        Used by SweepAuditJob, which must open its own Session.
        The flush event handlers never call this they write to the
        session that is already open, without touching the engine at all.
        """
        if self.engine is None:
            return None

        if isinstance(self.engine, AsyncEngine):
            return self.engine.sync_engine

        return self.engine

    def _wire_listeners(self) -> None:
        """
        Register before_flush / after_flush on the SQLAlchemy Session class.

        Idempotent the _listeners_wired flag on the registry  ensures listeners are registered exactly once
        even when configure_audit() is called multiple times.

        Both events fire on the underlying sync Session regardless of whether
        the caller used Session or AsyncSession.  No async-specific handling
        is needed in the handlers themselves.
        """

        if self._listeners_wired:
            return

        from sqlalchemy import event
        from sqlalchemy.orm import Session

        from lib.audit.helpers import after_flush, before_flush

        event.listen(Session, "before_flush", before_flush)
        event.listen(Session, "after_flush", after_flush)
        self._listeners_wired = True

        logger.debug("Audit: session listeners registered")


audit_registry = AuditRegistry()
