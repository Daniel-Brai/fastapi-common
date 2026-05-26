from datetime import datetime

from sqlmodel import TIMESTAMP, Field


class SoftDeletableMixin:
    """
    Mixin that adds a `deleted_at` flag to a model.

    Attributes:
        deleted_at (datetime | None): The datetime when the record was deleted.
    """

    deleted_at: datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=TIMESTAMP(timezone=True),  # type: ignore[assignment]
    )
