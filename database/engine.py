from sqlalchemy import Engine, create_engine, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_async_database_engine(
    database_url: str,
    *,
    pool_pre_ping: bool = True,
    pool_recycle: int = 3600,
    pool_size: int = 20,
    max_overflow: int = 10,
    echo: bool = False,
    use_null_pool: bool = False,
    **kwargs
) -> AsyncEngine:
    """
    Create an asynchronous SQLAlchemy engine and session factory.

    Args:
        database_url (str): The database connection URL.
        pool_pre_ping (bool): Whether to enable connection pre-ping. Default is True.
        pool_recycle (int): Number of seconds after which a connection is recycled. Default is 3600 (1 hour).
        pool_size (int): The size of the connection pool. Default is 20.
        max_overflow (int): The maximum number of connections to allow in overflow. Default is 10.
        echo (bool): If True, the engine will log all statements.
        use_null_pool (bool): If True, use NullPool to disable connection pooling.
        **kwargs: Additional keyword arguments to pass to the engine creation function.

    Returns:
        AsyncEngine: An asynchronous SQLAlchemy engine instance.
    """
    if use_null_pool:
        kwargs["poolclass"] = pool.NullPool
    else:
        kwargs["pool_pre_ping"] = pool_pre_ping
        kwargs["pool_recycle"] = pool_recycle
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow

    engine = create_async_engine(url=database_url, echo=echo, **kwargs)

    return engine


def create_database_engine(
    database_url: str,
    *,
    pool_pre_ping: bool = True,
    pool_recycle: int = 3600,
    pool_size: int = 20,
    max_overflow: int = 10,
    echo: bool = False,
    use_null_pool: bool = False,
    **kwargs
) -> Engine:
    """
    Create a synchronous SQLAlchemy engine.

    Args:
        database_url (str): The database connection URL.
        pool_pre_ping (bool): Whether to enable connection pre-ping. Default is True.
        pool_recycle (int): Number of seconds after which a connection is recycled. Default is 3600 (1 hour).
        pool_size (int): The size of the connection pool. Default is 20.
        max_overflow (int): The maximum number of connections to allow in overflow. Default is 10.
        echo (bool): If True, the engine will log all statements.
        use_null_pool (bool): If True, use NullPool to disable connection pooling.
        **kwargs: Additional keyword arguments to pass to the engine creation function.

    Returns:
        Engine: A synchronous SQLAlchemy engine instance.
    """
    if use_null_pool:
        kwargs["poolclass"] = pool.NullPool
    else:
        kwargs["pool_pre_ping"] = pool_pre_ping
        kwargs["pool_recycle"] = pool_recycle
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = max_overflow

    engine = create_engine(url=database_url, echo=echo, **kwargs)

    return engine
