from typing import Any

from sqlalchemy import Executable, create_engine, text
from sqlalchemy.pool import NullPool

from lib.logger import get_logger

logger = get_logger("lib.database.utils")


def ping_database(database_url: str) -> bool:
    """
    Pings the database to check if it's reachable.

    Args:
        database_url (str): The PostgreSQL database URI (sync).

    Returns:
        bool: True if the database is reachable, False otherwise.
    """

    logger.info("Pinging database...")

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
        echo=False,
    )

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info("Database is reachable.")
        return True
    except Exception as e:
        logger.error(f"Failed to ping database: {e}")
        return False
    finally:
        engine.dispose()


def run_sql(database_url: str, executables: list[Executable | Any], params: list[dict[str, Any]] | None = None) -> None:
    """
    Executes a list of database executables (e.g., triggers, functions, or any SQL statements) using a synchronous connection.

    Args:
        database_url (str): The PostgreSQL database URI (sync).
        executables (list[Executable]): A list of compiled SQLAlchemy text() or executable constructs to run.
        params (list[dict[str, Any]] | None): A list of dictionaries containing parameters for the SQL statements.
    """

    logger.info("Applying database executions...")

    if len(executables) == 0:
        logger.info("No executables to apply.")
        return

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
        echo=False,
    )

    try:
        with engine.begin() as conn:
            for i, executable in enumerate(executables):
                if isinstance(executable, str):
                    conn.exec_driver_sql(executable, params[i] if params else {})
                else:
                    conn.execute(executable, params[i] if params else {})

        logger.info("Successfully applied all executions.")
    except Exception as e:
        logger.error(f"Failed to apply executions: {e}")
        raise e
    finally:
        engine.dispose()
