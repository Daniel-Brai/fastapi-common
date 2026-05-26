import inflection
from sqlalchemy.orm import declared_attr
from sqlmodel import SQLModel


class BaseMixin(SQLModel):
    """
    A base mixin for models

    It provides the table name generation with inflection

    Basically, it converts the class name to snake_case and pluralizes it to create the table name.

    For example, if you have a model class named `User`, the table name will be generated as `users`.

    If you have a model class named `OrderItem`, the table name will be generated as `order_items`.
    """

    @declared_attr  # type: ignore
    def __tablename__(cls) -> str:  # type: ignore
        return inflection.pluralize(inflection.underscore(cls.__name__))
