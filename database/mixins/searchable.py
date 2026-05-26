from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field


class SearchableMixin:
    """
    Mixin for models that support full-text search.

    Attributes:
        search_vector (str | None): The search vector for full-text search.

    You will need to set the index on this column manually in a table argument of the model, e.g.:

        Index("ix_admin_search_vector", "search_vector", postgresql_using="gin"),
    """

    search_vector: str | None = Field(
        sa_type=TSVECTOR(),  # type: ignore[assignment]
        default=None,
        nullable=True,
    )
