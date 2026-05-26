from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """
    Recursively merge *override* into *base* in-place
    """

    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
