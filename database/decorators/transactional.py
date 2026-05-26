import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec

from sqlalchemy.orm import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.database.transaction import Transaction

P = ParamSpec("P")


def _resolve_session_argument(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    session_arg: str,
) -> Session | AsyncSession:

    signature = inspect.signature(func)
    bound = signature.bind_partial(*args, **kwargs)
    session = bound.arguments.get(session_arg)

    if not isinstance(session, (Session, AsyncSession)):
        raise ValueError(f"{func.__name__} must receive '{session_arg}' as a Session or AsyncSession")

    return session


def transactional(*, session_arg: str = "session") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorate a function with automatic transaction handling.

    The decorated function must receive a SQLAlchemy session argument
    (default name: ``session``) that is either ``Session`` or ``AsyncSession``.

    The decorator will manage transactions by committing if the function
    completes successfully, or rolling back if an exception is raised.


    Example:

    ```python
    from lib.database import transactional

    @transactional()
    def create_user(name: str, session: DBSession):
        user = User(name=name)
        session.add(user)
        session.flush()  # Ensure the user gets an ID assigned
        return user
    ```
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                session = _resolve_session_argument(func, args, kwargs, session_arg)
                if isinstance(session, AsyncSession):
                    async with Transaction(session):
                        return await func(*args, **kwargs)

                with Transaction(session):
                    return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            session = _resolve_session_argument(func, args, kwargs, session_arg)
            if isinstance(session, AsyncSession):
                raise TypeError(f"{func.__name__} is sync but received AsyncSession; use 'async def'")

            with Transaction(session):
                return func(*args, **kwargs)

        return sync_wrapper

    return decorator
