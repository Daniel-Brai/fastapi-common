import inspect
from typing import Any, Callable


async def maybe_await(value: Any) -> Any:
    """
    Check if *value* is awaitable, and if so, await it and return the result. 
    
    Otherwise, return *value* as-is.

    Args:
        value (Any): The value to check and potentially await.

    Returns:
        Any: The result of awaiting *value* if it is awaitable, or *value* itself if it is not.
    """

    if inspect.isawaitable(value):
        return await value

    return value


def attach(func: Callable[..., Any], marker: str, spec: dict[Any, Any]) -> Callable[..., Any]:
    """
    Append *spec* to the list stored at ``func.<marker>``.

    This is used by all the public decorators to attach their metadata to the decorated function.  
    
    The machine will look for these markers when building the transition graph.
    """

    if not hasattr(func, marker):
        setattr(func, marker, [])

    getattr(func, marker).append(spec)

    return func