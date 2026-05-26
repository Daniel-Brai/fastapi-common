from enum import StrEnum


class AuditAction(StrEnum):
    """
    Enumeration of possible audit actions.

    These are used to categorize audit log entries and can be extended as needed.

    Attributes:
        CREATE (str, "create"): Represents the creation of a new record.
        UPDATE (str, "update"): Represents the update of an existing record.
        DESTROY (str, "destroy"): Represents the destruction of a record.
    """

    CREATE = "create"
    UPDATE = "update"
    DESTROY = "destroy"
