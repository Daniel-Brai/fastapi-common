from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock


class MockExecResult:
    """
    A mock result object returned by MockAsyncSession.exec() and execute().
    """

    def __init__(self, items: list[Any] | tuple[Any, ...] = (), scalar_value: Any = None) -> None:
        self._items = list(items)
        self._scalar_value = scalar_value
        self.rowcount = len(self._items)

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any | None:
        return self._items[0] if self._items else None

    def one(self) -> Any:
        if not self._items:
            raise Exception("No result found")

        return self._items[0]

    def one_or_none(self) -> Any | None:
        return self._items[0] if self._items else None

    def scalar(self) -> Any:
        return self._scalar_value if self._scalar_value is not None else (self._items[0] if self._items else None)

    def scalar_one(self) -> Any:
        if self._scalar_value is not None:
            return self._scalar_value

        if not self._items:
            raise Exception("No scalar result found")

        return self._items[0]

    def scalar_one_or_none(self) -> Any | None:
        if self._scalar_value is not None:
            return self._scalar_value

        return self._items[0] if self._items else None

    def scalars(self) -> "_ScalarsProxy":
        return _ScalarsProxy(self._items)

    def unique(self) -> "_UniqueProxy":
        return _UniqueProxy(self._items)


class _UniqueProxy:
    def __init__(self, items: list[Any]) -> None:
        seen: set[int] = set()
        self._items = []

        for item in items:
            if id(item) not in seen:
                seen.add(id(item))
                self._items.append(item)

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any | None:
        return self._items[0] if self._items else None

    def one_or_none(self) -> Any | None:
        return self._items[0] if self._items else None

    def one(self) -> Any:
        if not self._items:
            raise Exception("No result found")

        return self._items[0]

    def scalars(self) -> "_ScalarsProxy":
        return _ScalarsProxy(self._items)


class _ScalarsProxy:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any | None:
        return self._items[0] if self._items else None

    def unique(self) -> "_UniqueProxy":
        return _UniqueProxy(self._items)


class MockTransaction:
    """
    A mock transaction object that mimics a SQLAlchemy transaction context manager.
    """

    def __init__(self, session: "MockAsyncSession") -> None:
        self._session = session
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            self.committed = True
            await self._session.commit()
        else:
            self.rolled_back = True
            await self._session.rollback()

        return False  # never suppress exceptions


class MockAsyncSession:
    """
    A mock async session that mimics the interface of SQLAlchemy's AsyncSession for testing purposes.
    """

    def __init__(self) -> None:
        self.exec = AsyncMock(return_value=MockExecResult())
        self.execute = AsyncMock(return_value=MockExecResult())
        self.get = AsyncMock(return_value=None)
        self.delete = AsyncMock()
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
        self.refresh = AsyncMock()
        self.add = MagicMock()
        self.add_all = MagicMock()
        self._last_transaction: MockTransaction | None = None
        self.sync_session = MagicMock()

    async def __aenter__(self) -> "MockAsyncSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    def begin(self) -> MockTransaction:
        tx = MockTransaction(self)
        self._last_transaction = tx
        return tx

    def set_exec_result(self, items: list[Any]) -> None:
        result = MockExecResult(items=items)
        self.exec.return_value = result
        self.execute.return_value = result

    def set_scalar_result(self, value: Any) -> None:
        result = MockExecResult(items=[value], scalar_value=value)
        self.exec.return_value = result
        self.execute.return_value = result

    def set_exec_sequence(self, *results: list[Any]) -> None:
        self.exec.side_effect = [MockExecResult(items=r) for r in results]
        self.execute.side_effect = [MockExecResult(items=r) for r in results]

    def reset(self) -> None:
        for attr in ("exec", "execute", "get", "delete", "flush", "commit", "rollback", "close", "refresh"):
            getattr(self, attr).reset_mock()

        self.add.reset_mock()
        self.add_all.reset_mock()
        self._last_transaction = None
