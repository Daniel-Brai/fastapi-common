from typing import Any, Callable, Optional, Union, get_args, get_origin, overload

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo


def _make_fields_optional(model_class: type[BaseModel], exclude_fields: list[str] | None = None) -> type[BaseModel]:
    fields = model_class.model_fields
    exclude_set = set(exclude_fields or [])

    new_fields: dict[str, Any] = {}

    for field_name, field_info in fields.items():
        if field_name in exclude_set:
            continue

        original_annotation = field_info.annotation

        from pydantic_core import PydanticUndefined

        has_default = field_info.default is not PydanticUndefined
        has_default_factory = field_info.default_factory is not None

        is_already_optional = get_origin(original_annotation) is Union and type(None) in get_args(original_annotation)

        if has_default or has_default_factory or is_already_optional:
            new_fields[field_name] = (original_annotation, field_info)
        else:
            new_annotation = Optional[original_annotation]
            new_field_info = FieldInfo(
                default=None,
                description=field_info.description,
                title=field_info.title,
                alias=field_info.alias,
                validation_alias=field_info.validation_alias,
                serialization_alias=field_info.serialization_alias,
                examples=field_info.examples,
                exclude=field_info.exclude,
                json_schema_extra=field_info.json_schema_extra,
                frozen=field_info.frozen,
                validate_default=field_info.validate_default,
                repr=field_info.repr,
                init=field_info.init,
                init_var=field_info.init_var,
                kw_only=field_info.kw_only,
                discriminator=field_info.discriminator,
            )
            new_fields[field_name] = (new_annotation, new_field_info)

    new_model_name = f"{model_class.__name__}Optional"
    new_model = create_model(new_model_name, **new_fields, __base__=BaseModel)

    if model_class.__doc__:
        new_model.__doc__ = f"Optional version of {model_class.__name__}. {model_class.__doc__}"

    return new_model


@overload
def optional(cls: type[BaseModel]) -> type[BaseModel]: ...


@overload
def optional(*, exclude_fields: list[str] | None = None) -> Callable[[type[BaseModel]], type[BaseModel]]: ...


def optional(
    cls: type[BaseModel] | None = None, *, exclude_fields: list[str] | None = None
) -> type[BaseModel] | Callable[[type[BaseModel]], type[BaseModel]]:
    """
    A class decorator that makes all fields of a Pydantic model optional.

    Example:

        ## Using a pydantic model:

        class User(BaseModel):
            id: int
            name: str

        ## Can be used as:

            @optional
            class UserUpdate(User):
                pass

            ## It is equivalent to:

            class UserUpdate(BaseModel):
                id: Optional[int] = None
                name: Optional[str] = None

        ## or with excluded fields removed entirely:

            @optional(exclude_fields=['id'])
            class UserUpdate(User):
                pass

            ## It is equivalent to:
            class UserUpdate(BaseModel):
                name: Optional[str] = None
    """

    if cls is None:
        return lambda cls: _make_fields_optional(cls, exclude_fields=exclude_fields)

    if not isinstance(cls, type) or not issubclass(cls, BaseModel):
        raise TypeError("@optional can only be used on Pydantic BaseModel subclasses")

    return _make_fields_optional(cls, exclude_fields=exclude_fields)
