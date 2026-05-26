import unittest
from typing import Any, Type

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.testing.database import MockAsyncSession

from .mixins import ServiceTestMixin
from .types import TransactionPatch


class TestServiceCase(unittest.IsolatedAsyncioTestCase, ServiceTestMixin):
    """
    Unittest-style base for testing service classes with a mocked database session.
    """

    service_class: Type[Any] | None = None

    async def asyncSetUp(self) -> None:
        if self.service_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `service_class`.")

        self.db = MockAsyncSession()
        self.service = self.service_class(self.db)
        self.service.transaction = TransactionPatch(self.db)

    async def asyncTearDown(self) -> None:
        self.db.reset()

    def assert_committed(self) -> None:
        """
        Assert `commit()` was called at least once.
        """
        self.db.commit.assert_called()

    def assert_not_committed(self) -> None:
        """
        Assert `commit()` was never called.
        """

        self.db.commit.assert_not_called()

    def assert_rolled_back(self) -> None:
        """
        Assert `rollback()` was called.
        """
        self.db.rollback.assert_called()

    def assert_transaction_committed(self) -> None:
        """
        Assert the last transaction() context exited cleanly
        """

        tx = self.db._last_transaction
        self.assertIsNotNone(tx, "No transaction was started.")
        self.assertTrue(tx.committed, "Transaction was not committed.")  # type: ignore

    def assert_transaction_rolled_back(self) -> None:
        """
        Assert the last transaction() context caught an exception.
        """
        tx = self.db._last_transaction
        self.assertIsNotNone(tx, "No transaction was started.")
        self.assertTrue(tx.rolled_back, "Transaction was not rolled back.")  # type: ignore

    def assert_flushed(self) -> None:
        """
        Assert `flush()` was called (repo wrote to the session).
        """

        self.db.flush.assert_called()


class TestIORunnableServiceCase(unittest.IsolatedAsyncioTestCase, ServiceTestMixin):
    """
    Base for testing `IORunnableService` subclasses in unit-test style with a mocked database.
    """

    service_class: Type[Any] | None = None

    async def asyncSetUp(self) -> None:
        if self.service_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `service_class`.")
        self.db = MockAsyncSession()
        self.service = self.service_class(self.db)

    async def asyncTearDown(self) -> None:
        self.db.reset()

    def assert_committed(self) -> None:
        self.db.commit.assert_called()

    def assert_not_committed(self) -> None:
        self.db.commit.assert_not_called()

    def assert_flushed(self) -> None:
        self.db.flush.assert_called()


class TestRunnableServiceCase(unittest.IsolatedAsyncioTestCase, ServiceTestMixin):
    """
    Base for testing `RunnableService` and `StandaloneRunnableService` subclasses in unit-test style
    """

    service_class: Type[Any] | None = None

    async def asyncSetUp(self) -> None:
        if self.service_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `service_class`.")
        self.service = self.service_class()

    async def asyncTearDown(self) -> None:
        pass


class TestServiceIntegrationCase(unittest.IsolatedAsyncioTestCase, ServiceTestMixin):
    """
    Base for testing service classes for integration-style tests that interact with the database.
    """

    service_class: Type[Any] | None = None
    db_engine: AsyncEngine | None = None
    db_session_factory: Any | None = None

    async def asyncSetUp(self) -> None:
        if self.service_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `service_class`.")
        if self.db_session_factory is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `db_session_factory`.")
        if self.db_engine is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `db_engine`.")

        await self._clear_tables()

        self.db: AsyncSession = self.db_session_factory()
        self.service = self.service_class(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        await self.db_session_factory.remove()  # type: ignore

    async def _clear_tables(self) -> None:
        from sqlalchemy import text
        from sqlmodel import SQLModel

        assert self.db_engine is not None, "engine must be set to clear tables."

        async with self.db_engine.connect() as conn:
            for table in reversed(SQLModel.metadata.sorted_tables):
                await conn.execute(text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE"))
            await conn.commit()


class TestIORunnableServiceIntegrationCase(unittest.IsolatedAsyncioTestCase, ServiceTestMixin):
    """
    Base for testing `IORunnableService` subclasses to be used in integration-style tests that interact with the database.
    """

    service_class: Type[Any] | None = None
    db_engine: AsyncEngine | None = None
    db_session_factory: Any | None = None

    async def asyncSetUp(self) -> None:
        if self.service_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `service_class`.")
        if self.db_session_factory is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `db_session_factory`.")
        if self.db_engine is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `db_engine`.")

        await self._clear_tables()

        self.db: AsyncSession = self.db_session_factory()
        self.service = self.service_class(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        await self.db_session_factory.remove()  # type: ignore

    async def _clear_tables(self) -> None:
        from sqlalchemy import text
        from sqlmodel import SQLModel

        assert self.db_engine is not None, "engine must be set to clear tables."

        async with self.db_engine.connect() as conn:
            for table in reversed(SQLModel.metadata.sorted_tables):
                await conn.execute(text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE"))

            await conn.commit()
