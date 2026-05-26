class AuditError(Exception):
    """
    Base exception for the audit library.
    """

    pass


class AuditNotConfigured(RuntimeError):
    """
    Raised when an audit operation is attempted before the registry is configured.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "Audit is not configured. Call configure_audit() at application startup.")


class AuditModelNotRegistered(AuditError):
    """
    Raised when querying audits for a model that was not registered.
    """

    def __init__(self, model) -> None:
        super().__init__(
            f"{model.__name__} is not audited. " f"Add AuditedMixin to the class and call configure_audit()."
        )
