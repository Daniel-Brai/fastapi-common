from typing import Any
from uuid import UUID, uuid4, uuid7

from pydantic import field_validator
from sqlmodel import Field

from lib.database.mixins.base import BaseMixin


class IntegerIDMixin(BaseMixin):
    """
    A mixin for models with an integer primary key.

    Attributes:
        id (int): The primary key field.
    """

    id: int = Field(index=True, primary_key=True)


class UUID4Mixin(BaseMixin):
    """
    A mixin for models with a UUID primary key.

    Attributes:
        id (UUID): The primary key field.
    """

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )


class UUID7Mixin(BaseMixin):
    """
    A mixin for models with a UUID7 primary key.

    Attributes:
        id (UUID): The primary key field.
    """

    id: UUID = Field(
        default_factory=uuid7,
        primary_key=True,
        index=True,
        nullable=False,
    )


class CompositeIDMixin[T: tuple](BaseMixin):
    """
    A mixin for models with composite primary keys.

    This mixin provides methods for handling composite keys properly in SQLModel.
    The generic type T should be a tuple of the types of your primary key fields.

    Attributes:
        id (T): The composite primary key field.

    Example:

        ```python
        from sqlmodel import SQLModel, Field
        from lib.database.mixins import CompositeIDMixin

        class OrderItem(CompositeIDMixin[tuple[int, int]], table=True):
            order_id: int = Field(primary_key=True)
            item_id: int = Field(primary_key=True)
            quantity: int
        ```
    """

    @classmethod
    def get_composite_key_fields(cls) -> list[str]:
        model_fields = cls.model_fields
        return [
            field_name
            for field_name, field in model_fields.items()
            if field.json_schema_extra and dict(getattr(field, "json_schema_extra", {})).get("primary_key", False)
        ]

    def get_composite_key(self) -> T:
        key_fields = self.get_composite_key_fields()
        return tuple(getattr(self, field) for field in key_fields)  # type: ignore

    @field_validator("*", mode="before")
    @classmethod
    def validate_composite_keys(cls, v: Any, info: Any) -> Any:
        field_name = info.field_name
        field = cls.model_fields.get(field_name)
        if not field:
            return v

        # NOTE: Here we skip validation for non-primary key fields
        if not (field.json_schema_extra and dict(getattr(field, "json_schema_extra", {})).get("primary_key", False)):
            return v

        if v is None:
            raise ValueError(f"Primary key field '{field_name}' cannot be None")

        return v
