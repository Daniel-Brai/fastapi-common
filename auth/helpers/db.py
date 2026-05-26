from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


def is_async_engine(engine: Any) -> bool:
    """
    Return True when engine is a SQLAlchemy AsyncEngine.
    """

    if engine is None:
        return False
    try:
        from sqlalchemy.ext.asyncio import AsyncEngine

        return isinstance(engine, AsyncEngine)
    except ImportError:
        return False


@asynccontextmanager
async def db_session() -> AsyncIterator[Any]:
    """
    Async context manager that yields a DB session appropriate for the engine.

    Always use with 'async with':

        async with db_session() as s:
            result = await db_exec(s, select(User).where(...))
            user   = result.first()
            await db_commit(s)
    """

    from lib.auth.config import get_registry

    registry = get_registry()

    if registry.is_async:
        from sqlalchemy.ext.asyncio import AsyncEngine
        from sqlmodel.ext.asyncio.session import AsyncSession

        assert isinstance(registry.db_engine, AsyncEngine)

        async with AsyncSession(registry.db_engine, expire_on_commit=False) as s:
            yield s
    else:
        from sqlalchemy import Engine
        from sqlalchemy.orm import Session

        assert isinstance(registry.db_engine, Engine)

        with Session(registry.db_engine) as s:
            yield s


async def db_exec(session: Any, stmt: Any) -> Any:
    """
    Execute a SQLModel or SQLAlchemy select statement.

    Awaits automatically when session is an AsyncSession.

    Examples:

        result = await db_exec(s, select(User).where(User.email == email))
        user   = result.first()
    """

    from lib.auth.config import get_registry

    if get_registry().is_async:
        return await session.exec(stmt)

    return session.exec(stmt)


async def db_get(session: Any, model: type, pk: Any) -> Any:
    """
    Retrieve a row by primary key.

    Awaits automatically when session is an AsyncSession.

        user = await db_get(s, User, user_id)
    """
    from lib.auth.config import get_registry

    if get_registry().is_async:
        return await session.get(model, pk)

    return session.get(model, pk)


async def db_commit(session: Any) -> None:
    """
    Commit the session, awaiting when async.
    """
    from lib.auth.config import get_registry

    if get_registry().is_async:
        await session.commit()
    else:
        session.commit()


async def db_refresh(session: Any, obj: Any) -> None:
    """
    Refresh an ORM object from the DB, awaiting when async.
    """
    from lib.auth.config import get_registry

    if get_registry().is_async:
        await session.refresh(obj)
    else:
        session.refresh(obj)


async def db_add_commit_refresh(session: Any, obj: Any) -> Any:
    """
    Add obj, commit, and refresh
    """

    session.add(obj)
    await db_commit(session)
    await db_refresh(session, obj)
    return obj
