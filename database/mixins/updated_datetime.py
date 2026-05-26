from datetime import datetime

from sqlmodel import TIMESTAMP, Field, func


class UpdatedDateTimeMixin:
    """
    Mixin that adds `updated_at` column to a model

    Attributes:
        updated_at (datetime | None): The datetime when the record was last updated.
    """

    updated_at: datetime | None = Field(
        sa_type=TIMESTAMP(timezone=True),  # type: ignore[assignment]
        nullable=True,
        default=None,
        sa_column_kwargs={"onupdate": func.now()},
    )
