from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError, core_schema
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

type DBEngine = Engine | AsyncEngine


_PASSWORD_SPECIAL_CHARACTERS = frozenset(
    {
        "!",
        "@",
        "#",
        "$",
        "%",
        "^",
        "&",
        "*",
        "(",
        ")",
        "-",
        "_",
        "=",
        "+",
        "{",
        "}",
        "[",
        "]",
        "|",
        "\\",
        ":",
        ";",
        "'",
        '"',
        "<",
        ">",
        ",",
        ".",
        "?",
        "/",
    }
)


class Password(str):
    """
    Pydantic type for password
    """

    special_chars: frozenset[str] = _PASSWORD_SPECIAL_CHARACTERS
    min_length: int = 8
    max_length: int = 128
    includes_special_chars: bool = True
    includes_numbers: bool = True
    includes_lowercase: bool = True
    includes_uppercase: bool = True

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema.update(
            minLength=cls.min_length,
            maxLength=cls.max_length,
            includesNumbers=cls.includes_numbers,
            includesLowercase=cls.includes_lowercase,
            includesUppercase=cls.includes_uppercase,
            includesSpecialChars=cls.includes_special_chars,
            specialChars=list(cls.special_chars),
        )
        return json_schema

    @classmethod
    def validate(cls, value: Any) -> "Password":
        errors = []

        if not isinstance(value, str):
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError("value_error", "Pssword should be a string"),
                    input=value,
                )
            )

        if len(value) < cls.min_length:
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError(
                        "string_too_short",
                        "Password should be at least {min_length} characters",
                        {"min_length": cls.min_length},
                    ),
                    input=value,
                )
            )

        if len(value) > cls.max_length:
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError(
                        "string_too_long",
                        "Password should not exceed {max_length} characters",
                        {"max_length": cls.max_length},
                    ),
                    input=value,
                )
            )

        if cls.includes_numbers and not any(char.isdigit() for char in value):
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError("value_error", "Password should have at least one digit"),
                    input=value,
                )
            )

        if cls.includes_uppercase and not any(char.isupper() for char in value):
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError(
                        "value_error",
                        "Password should have at least one uppercase letter",
                    ),
                    input=value,
                )
            )
        if cls.includes_lowercase and not any(char.islower() for char in value):
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError(
                        "value_error",
                        "Password should have at least one lowercase letter",
                    ),
                    input=value,
                )
            )

        if cls.includes_special_chars and not any(char in cls.special_chars for char in value):
            errors.append(
                InitErrorDetails(
                    type=PydanticCustomError(
                        "value_error",
                        "Password should have at least one encodable special character",
                    ),
                    input=value,
                )
            )

        if errors:
            raise ValidationError.from_exception_data(
                title="invalid_password",
                line_errors=errors,
            )

        return cls(value)

    def __repr__(self) -> str:
        return f"Password('{self!s}')"
