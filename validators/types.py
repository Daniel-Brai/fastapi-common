from typing import Any, Optional


def validate_bool(true_values: set[str] | None = None, false_values: set[str] | None = None):
    """
    Parse a conformable type into a boolean.

    Args:
        true_values (set[str] | None): A set of string values that should be interpreted as True.
        false_values (set[str] | None): A set of string values that should be interpreted as False.

    Returns:
        A function that takes a value and returns a boolean.
    """

    if true_values is None:
        true_values = {"true", "1", "yes", "on", "t", "y"}
    if false_values is None:
        false_values = {"false", "0", "no", "off", "f", "n"}

    def parser(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            lower = v.lower().strip()
            if lower in true_values:
                return True
            if lower in false_values:
                return False
            raise ValueError(f"Cannot parse '{v}' as boolean")
        if isinstance(v, int):
            return bool(v)
        raise ValueError(f"Cannot convert {type(v)} to bool")

    return parser


def validate_string(replace_empty_with_none: bool = True):
    """
    Parse a value into a string, with an option to convert empty strings to None.

    Args:
        replace_empty_with_none (bool): If True, empty strings will be converted to None.

    Returns:
        A function that transforms '' into None and leaves other values unchanged.
    """

    def parser(v: Any) -> Any:
        if replace_empty_with_none and v == "":
            return None
        return v

    return parser


def validate_list[T](obj: Optional[T] = None):
    """
    Parse a conformable type into a list of items.

    Args:
        obj (Optional[T] | Any): An optional type constructor to convert each item.

    Returns:
        A function that takes a value and returns a list of items of type T.
    """

    def parser(v: Any):
        if v is None:
            return None

        if isinstance(v, dict):
            try:
                items = [v[k] for k in sorted(v.keys(), key=lambda x: int(x))]
            except Exception:
                items = list(v.values())
        elif isinstance(v, list):
            items = v
        else:
            value = str(v)
            items = value.split(",") if value != "" else []

        flattened: list[Any] = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, list):
                flattened.extend(item)
            else:
                pieces = str(item).split(",")
                for p in pieces:
                    piece = p.strip()
                    if piece:
                        flattened.append(piece)

        if obj and flattened:
            try:
                return [obj(item) if not isinstance(item, obj) else item for item in flattened]  # type: ignore
            except Exception:
                return [obj(str(item)) if not isinstance(item, obj) else item for item in flattened]  # type: ignore

        return flattened

    return parser
