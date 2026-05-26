import unittest
from typing import Any, Callable, Type

from fastapi import status
from fastapi.testclient import TestClient

from lib.testing.helpers import build_app

from .browser import BrowserSession


class TestViewCase(unittest.IsolatedAsyncioTestCase):
    """
    Unittest base for HTML view tests.
    """

    view_class: Type[Any] | None = None

    def get_dependency_overrides(self) -> dict[Callable, Callable]:
        return {}

    def get_build_options(self) -> dict[str, list[str] | None]:
        """
        Options for building the test app. Passed to `build_app` helper.
        """
        return {}

    async def asyncSetUp(self) -> None:
        if self.view_class is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set `view_class`.")

        self.app = build_app(self.view_class, **self.get_build_options())
        self.app.dependency_overrides.update(self.get_dependency_overrides())

        client = TestClient(self.app, raise_server_exceptions=True)
        self.browser = BrowserSession(client)

    async def asyncTearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def override_dependency(self, original: Callable, override: Callable) -> None:
        self.app.dependency_overrides[original] = override

    def visit(self, path: str, **kwargs) -> None:
        self.browser.visit(path, **kwargs)

    def click(self, selector: str, **kwargs) -> None:
        self.browser.click(selector, **kwargs)

    def fill_in_form(self, form_selector: str, field_selector: str, value: str) -> None:
        self.browser.fill_in_form(form_selector, field_selector, value)

    def submit(self, form_selector: str | None = None, **kwargs) -> None:
        self.browser.submit(form_selector=form_selector, **kwargs)

    def assert_status(self, code: int) -> None:
        self.browser.assert_status(code)

    def assert_ok(self) -> None:
        self.browser.assert_status(status.HTTP_200_OK)

    def assert_no_content(self) -> None:
        self.browser.assert_status(status.HTTP_204_NO_CONTENT)

    def assert_permanently_moved(self) -> None:
        self.browser.assert_status(status.HTTP_301_MOVED_PERMANENTLY)

    def assert_found(self) -> None:
        self.browser.assert_status(status.HTTP_302_FOUND)

    def assert_temporary_redirect(self) -> None:
        self.browser.assert_status(status.HTTP_307_TEMPORARY_REDIRECT)

    def assert_permanent_redirect(self) -> None:
        self.browser.assert_status(status.HTTP_308_PERMANENT_REDIRECT)

    def assert_unauthorized(self) -> None:
        self.browser.assert_status(status.HTTP_401_UNAUTHORIZED)

    def assert_forbidden(self) -> None:
        self.browser.assert_status(status.HTTP_403_FORBIDDEN)

    def assert_not_found(self) -> None:
        self.browser.assert_status(status.HTTP_404_NOT_FOUND)

    def assert_server_error(self) -> None:
        self.browser.assert_status(status.HTTP_500_INTERNAL_SERVER_ERROR)

    def assert_contains(self, text: str, case_sensitive: bool = True) -> None:
        self.browser.assert_contains(text, case_sensitive=case_sensitive)

    def assert_selector(self, selector: str, count: int | None = None) -> None:
        self.browser.assert_selector(selector, count=count)
