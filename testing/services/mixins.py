import inspect
from typing import Any, Type
from unittest.mock import AsyncMock, MagicMock


class ServiceTestMixin:
    """
    Mixin for service tests
    """

    def mock_repo(self, repo_class: Type[Any], **overrides: Any) -> MagicMock:
        """
        Build a MagicMock spec'd to *repo_class* with all coroutine methods
        promoted to AsyncMock automatically.

        Pass explicit overrides for methods you want to configure up-front:

            self.service.feed_repo = self.mock_repo(
                FeedRepository,
                get_by=AsyncMock(return_value=None),
                create=AsyncMock(return_value=fake_feed),
            )
        """

        mock = MagicMock(spec=repo_class)

        for name in dir(repo_class):
            if name.startswith("_"):
                continue
            attr = getattr(repo_class, name, None)
            if attr is not None and callable(attr) and inspect.iscoroutinefunction(attr):
                setattr(mock, name, AsyncMock())

        for name, value in overrides.items():
            setattr(mock, name, value)

        return mock

    def mock_service(self, service_class: Type[Any], **overrides: Any) -> MagicMock:
        """
        Build a MagicMock spec'd to *service_class* for when a service
        depends on another service (e.g. FeedPollerService → FeedFetcherService).

            self.service.feed_fetcher_svc = self.mock_service(FeedFetcherService)
            self.service.feed_fetcher_svc.run = AsyncMock()
        """

        mock = MagicMock(spec=service_class)

        for name in dir(service_class):
            if name.startswith("_"):
                continue
            attr = getattr(service_class, name, None)
            if attr is not None and callable(attr) and inspect.iscoroutinefunction(attr):
                setattr(mock, name, AsyncMock())

        for name, value in overrides.items():
            setattr(mock, name, value)

        return mock
