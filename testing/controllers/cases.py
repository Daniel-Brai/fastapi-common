import unittest
from typing import Any, Callable, Type

from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.testing.helpers import build_app


class TestControllerCase(unittest.IsolatedAsyncioTestCase):
    """
    Unittest-style base for controller tests.

    Usage
    -----

    ```python
        class TestFeedController(TestControllerCase):
            controller_class = FeedController

            def get_dependency_overrides(self):
                return {get_feed_service: lambda: self.mock_service}

            async def asyncSetUp(self):
                await super().asyncSetUp()
                self.mock_service = AsyncMock(spec=FeedService)
                # Re-apply overrides AFTER mock is created
                self.app.dependency_overrides.update(
                    self.get_dependency_overrides()
                )

            async def test_list_feeds(self):
                self.mock_service.list_subscribed_feeds.return_value = ("ok", [], None)
                resp = await self.client.get("/feeds")
                self.assert_ok(resp)
    ```
    """

    controller_class: Type[Any] | None = None

    # Override to supply FastAPI dependency overrides.
    def get_dependency_overrides(self) -> dict[Callable, Callable]:
        return {}

    async def asyncSetUp(self) -> None:
        if self.controller_class is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set `controller_class`."
            )

        self.app = build_app(self.controller_class)

        overrides = self.get_dependency_overrides()
        self.app.dependency_overrides.update(overrides)

        self._async_transport = ASGITransport(app=self.app)
        self.client = AsyncClient(
            transport=self._async_transport,
            base_url="http://testserver",
        )

        await self.client.__aenter__()

    async def asyncTearDown(self) -> None:
        await self.client.__aexit__(None, None, None)
        self.app.dependency_overrides.clear()

    def override_dependency(self, original: Callable, override: Callable) -> None:
        """
        Add or replace a single dependency override at runtime.
        """

        self.app.dependency_overrides[original] = override

    def clear_overrides(self) -> None:
        self.app.dependency_overrides.clear()

    def assert_status(self, response: Any, status_code: int) -> None:
        self.assertEqual(
            response.status_code,
            status_code,
            f"Expected {status_code}, got {response.status_code}. Body: {response.text}",
        )

    def assert_ok(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_200_OK)

    def assert_no_content(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_204_NO_CONTENT)

    def assert_created(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_201_CREATED)

    def assert_permanently_moved(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_301_MOVED_PERMANENTLY)

    def assert_found(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_302_FOUND)

    def assert_temporary_redirect(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_307_TEMPORARY_REDIRECT)

    def assert_permanent_redirect(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_308_PERMANENT_REDIRECT)

    def assert_bad_request(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_400_BAD_REQUEST)

    def assert_unauthorized(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_401_UNAUTHORIZED)

    def assert_forbidden(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_403_FORBIDDEN)

    def assert_not_found(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_404_NOT_FOUND)

    def assert_conflict(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_409_CONFLICT)

    def assert_server_error(self, response: Any) -> None:
        self.assert_status(response, status.HTTP_500_INTERNAL_SERVER_ERROR)


class TestControllerIntegrationCase(TestControllerCase):
    """
    Base for testing controllers against a real database in integration style.
    """

    db_engine: AsyncEngine | None = None
    db_session_factory: Any | None = None

    async def asyncSetUp(self) -> None:
        if self.db_session_factory is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set `db_session_factory`."
            )
        if self.db_engine is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set `db_engine`."
            )

        await self._clear_tables()
        await super().asyncSetUp()
        self.db: AsyncSession = self.db_session_factory()

    async def asyncTearDown(self) -> None:
        await super().asyncTearDown()
        await self.db.close()
        await self.db_session_factory.remove()  # type: ignore

    async def _clear_tables(self) -> None:
        from sqlalchemy import text
        from sqlmodel import SQLModel

        assert self.db_engine is not None, "engine must be set to clear tables."

        async with self.db_engine.connect() as conn:
            for table in reversed(SQLModel.metadata.sorted_tables):
                await conn.execute(
                    text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE")
                )
            await conn.commit()
