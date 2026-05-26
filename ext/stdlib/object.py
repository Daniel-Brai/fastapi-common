from typing import Any


def delete_attribute(obj: Any, name: str):
    """
    Delete an attribute from an object if it exists.
    """

    if hasattr(obj, name):
        try:
            delattr(obj, name)
        except Exception:
            pass
