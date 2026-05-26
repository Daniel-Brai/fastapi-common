from datetime import datetime

from sqlmodel import TIMESTAMP, Field, func


class CreatedDateTimeMixin:
    """
    Mixin that adds `created_at` column to a model

    Attributes:
        created_at (datetime): The datetime when the record was created.
    """

    created_at: datetime = Field(
        sa_type=TIMESTAMP(timezone=True),  # type: ignore[assignment]
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
