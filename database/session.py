from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession


def create_async_session(
    engine: AsyncEngine,
    *,
    autocommit: bool = False,
    autoflush: bool = False,
    expire_on_commit: bool = False,
    **kwargs: Any,
):
    """
    Create an asynchronous SQLAlchemy session factory.

    Args:
        engine (AsyncEngine): The asynchronous SQLAlchemy engine to bind the session to.
        autocommit (bool): Whether to enable autocommit mode. Default is False.
        autoflush (bool): Whether to enable autoflush mode. Default is False.
        expire_on_commit (bool): Whether to expire objects on commit. Default is False.
        **kwargs: Additional keyword arguments to pass to the sessionmaker.

    Returns:
        An asynchronous SQLAlchemy session factory.


    Examples:

        ```python
        from lib.database import create_async_database_engine

        engine = create_async_database_engine("postgresql+asyncpg://user:password@localhost/dbname")

        session_factory = create_async_session(engine)
        ```
    """

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=autocommit,
        autoflush=autoflush,
        expire_on_commit=expire_on_commit,
        **kwargs,
    )


def create_session(
    engine: Engine,
    *,
    autocommit: bool = False,
    autoflush: bool = False,
    expire_on_commit: bool = False,
    **kwargs: Any,
):
    """
    Create a synchronous SQLAlchemy session factory.

    Args:
        engine (Any): The SQLAlchemy engine to bind the session to.
        autocommit (bool): Whether to enable autocommit mode. Default is False.
        autoflush (bool): Whether to enable autoflush mode. Default is False.
        expire_on_commit (bool): Whether to expire objects on commit. Default is False.
        **kwargs: Additional keyword arguments to pass to the sessionmaker.

    Returns:
        A SQLAlchemy session factory.

    Examples:

        ```python
        from lib.database import create_sync_database_engine

        engine = create_sync_database_engine("postgresql://user:password@localhost/dbname")

        session_factory = create_session(engine)
        ```
    """

    return sessionmaker(
        bind=engine,
        class_=Session,
        autocommit=autocommit,
        autoflush=autoflush,
        expire_on_commit=expire_on_commit,
        **kwargs,
    )


async def get_db_async_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get an asynchronous database session.

    Args:
        session_factory (async_sessionmaker[AsyncSession]): The session factory to create sessions from.

    Yields:
        AsyncSession: An asynchronous database session.

    Examples::

        FastAPI dependency usage:

        ```python
        from collections.abc import AsyncGenerator
        from typing import Annotated

        from fastapi import APIRouter, Depends
        from sqlalchemy import select
        from sqlmodel.ext.asyncio.session import AsyncSession

        from lib.database.engine import create_async_database_engine
        from lib.database.session import create_async_session, get_db_async_session

        engine = create_async_database_engine("postgresql+asyncpg://user:password@localhost/dbname")
        session_factory = create_async_session(engine)

        async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
            async with db_async_session_manager(session_factory) as session:
                yield session

        AsyncDBSession = Annotated[AsyncSession, Depends(get_async_db)]

        router = APIRouter()

        @router.get("/users/{user_id}")
        async def get_user(user_id: int, db: AsyncDBSession):
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.one_or_none()
            return {"user": user.id if user else None}
        ```
    """

    session = session_factory()
    try:
        yield session
    finally:
        await session.close()


def db_async_session_manager(session_factory: async_sessionmaker[AsyncSession]):
    return asynccontextmanager(get_db_async_session)(session_factory)


def get_db_session(
    session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    """
    Get a synchronous database session.

    Args:
        session_factory (sessionmaker[Session]): The session factory to create sessions from.

    Yields:
        Session: A synchronous database session.

    Examples:

        FastAPI dependency usage:

        ```python
        from collections.abc import Generator
        from typing import Annotated

        from fastapi import APIRouter, Depends
        from sqlalchemy.orm import Session

        from lib.database.engine import create_sync_database_engine
        from lib.database.session import create_session, get_db_session

        engine = create_sync_database_engine("postgresql://user:password@localhost/dbname")
        session_factory = create_session(engine)

        def get_sync_db() -> Generator[Session, None, None]:
            with db_session_manager(session_factory) as session:
                yield session

        DBSession = Annotated[Session, Depends(get_sync_db)]

        router = APIRouter()

        @router.get("/users/{user_id}")
        def get_user(user_id: int, db: DBSession):
            user = db.query(User).filter(User.id == user_id).one_or_none()
            return {"user": user.id if user else None}
        ```
    """

    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def db_session_manager(session_factory: sessionmaker[Session]):
    return contextmanager(get_db_session)(session_factory)
