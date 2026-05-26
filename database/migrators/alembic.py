from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from lib.logger import get_logger

logger = get_logger("lib.database.migrators.alembic")


def _get_alembic_config(database_url: str, alembic_ini_path: str | Path) -> Config:
    """
    Create an Alembic Config pointing to the project's alembic.ini
    """

    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("sqlalchemy.url", str(database_url))
    return cfg


def _get_db_current_revision(sync_connection) -> str | None:
    mc = MigrationContext.configure(sync_connection)
    return mc.get_current_revision()


def _get_head_revisions(cfg: Config) -> set:
    script = ScriptDirectory.from_config(cfg)
    return set(script.get_heads())


def run_migrations(
    database_url: str,
    alembic_ini_path: str | Path,
):
    """
    Checks DB revision and runs `alembic upgrade head` when the database is behind the latest migrations.

    Args:
        database_url (str): The SQLAlchemy database URL to connect to.
        alembic_ini_path (str | Path): Path to the alembic.ini file to use for configuration.

    Returns:
        None
    """

    cfg = _get_alembic_config(database_url, alembic_ini_path)

    heads = _get_head_revisions(cfg)
    logger.debug(f"Local alembic heads: {heads}")

    sync_engine = create_engine(
        database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
        echo=False,
    )

    try:
        logger.info("Attempting to connect to database...")
        with sync_engine.connect() as conn:
            current = _get_db_current_revision(conn)

        logger.debug(f"DB current revision: {current}")

        if current is None or current not in heads:
            logger.info(f"Database migrations are outdated (current={current}, heads={heads}). Upgrading...")
            command.upgrade(cfg, "head")
            logger.info("Database migrations upgraded to head")

        logger.info(f"Database migrations already up-to-date (current={current}).")
    except Exception as e:
        logger.error(f"Migration connection or execution error: {str(e)}")
        raise e
    finally:
        sync_engine.dispose()
        logger.debug("Migration engine disposed")
