from typing import Literal

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from requests import Response


class HTMLAssertionError(AssertionError):
    """
    A custom assertion error for HTML-related assertions in BrowserSession.
    """

    pass


class BrowserSession:
    """
    A session for testing HTML/HTMX views.

    It wraps TestClient and provides userfacing methods like visit, click, fill_in, fill_in_form, submit, and assertions.
    """

    def __init__(self, client: TestClient, base_url: str = ""):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.response: Response | None = None
        self.soup: BeautifulSoup | None = None
        self._form_data: dict = {}  # stores filled values per form

    def _url(self, path: str) -> str:
        """
        Make absolute URL from relative path.
        """
        if path.startswith(("http://", "https://")):
            return path

        return f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"

    def _update_response(self, response: Response) -> None:
        self.response = response
        self.soup = BeautifulSoup(response.text, "html.parser")

    def _make_request(
        self,
        method: Literal["get", "post", "put", "patch", "delete"],
        path: str,
        **kwargs,
    ) -> Response:
        """
        Perform HTTP request and store response/soup.
        """

        url = self._url(path)
        response = getattr(self.client, method)(url, **kwargs)
        self._update_response(response)
        return response

    def get(self, path: str, **kwargs) -> Response:
        return self._make_request("get", path, **kwargs)

    def post(self, path: str, **kwargs) -> Response:
        return self._make_request("post", path, **kwargs)

    def put(self, path: str, **kwargs) -> Response:
        return self._make_request("put", path, **kwargs)

    def patch(self, path: str, **kwargs) -> Response:
        return self._make_request("patch", path, **kwargs)

    def delete(self, path: str, **kwargs) -> Response:
        return self._make_request("delete", path, **kwargs)

    def visit(self, path: str, **kwargs) -> None:
        """
        Visit a page (GET) and store the response
        """
        self.get(path, **kwargs)

    def follow_redirect(self) -> None:
        """
        Follow the redirect from the last response.
        """
        if self.response and 300 <= self.response.status_code < 400:
            location = self.response.headers.get("location")
            if location:
                self.visit(location)
        else:
            raise RuntimeError("No redirect to follow")

    def click(self, selector: str, **kwargs) -> None:
        """
        Click a link (or any element) by CSS selector.

        If the element is an <a>, its href is visited.

        For other elements, you may need to override.
        """

        if not self.soup:
            raise RuntimeError("No page loaded")

        element = self.soup.select_one(selector)
        if not element:
            raise HTMLAssertionError(f"Element not found: {selector}")

        if element.name == "a":
            href = element.get("href")
            if href and href != "#":
                if isinstance(href, list):
                    href = href[0]
                self.visit(str(href), **kwargs)
                return

        if element.name == "button":
            btn_type = element.get("type")
            is_submit = btn_type is None or btn_type == "submit" or btn_type == ["submit"]
            if is_submit:
                form = element.find_parent("form")
                if form:
                    # Try to submit the form this button belongs to
                    form_id = form.get("id")
                    if form_id:
                        form_identifier = str(form_id[0]) if isinstance(form_id, list) else str(form_id)
                        self.submit(form_selector=f"#{form_identifier}", **kwargs)
                    else:
                        # Fallback to the default form submission
                        self.submit(**kwargs)
            return

        if element.has_attr("onclick"):
            # we do not execute JavaScript in this testing session wrapper,
            # but we explicitly allow clicking it without raising an error.
            return

        raise NotImplementedError(
            f"Click on {element.name} not implemented (only <a>, <button>, or elements with onclick)"
        )

    def fill_in(self, field_selector: str, value: str) -> None:
        """
        Fill a form field on the current page.

        The field is assumed to belong to the first form on the page.
        """

        self.fill_in_form(form_selector="form", field_selector=field_selector, value=value)

    def fill_in_form(self, form_selector: str, field_selector: str, value: str) -> None:
        """
        Fill a specific field inside a specific form.

        The form must be locatable by CSS selector.
        """

        if not self.soup:
            raise RuntimeError("No page loaded")

        form = self.soup.select_one(form_selector)
        if not form:
            raise HTMLAssertionError(f"Form not found: {form_selector}")

        field = form.select_one(field_selector)
        if not field:
            raise HTMLAssertionError(f"Field not found in form: {field_selector}")

        # Store the value under this form selector and field selector
        self._form_data.setdefault(form_selector, {})[field_selector] = value

    def submit(self, form_selector: str | None = None, **kwargs) -> None:
        """
        Submit a form.

        If form_selector is given, that specific form is used; otherwise the first form.

        Form data from previous fill_in/fill_in_form calls is combined with the actual form's fields (hidden inputs, etc.).
        """

        if not self.soup:
            raise RuntimeError("No page loaded")

        if form_selector:
            form = self.soup.select_one(form_selector)
        else:
            form = self.soup.find("form")
        if not form:
            raise HTMLAssertionError("No form found")

        def _normalize_attr(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, list):
                return str(value[0]) if value else ""
            return str(value)

        action_attr = form.get("action")
        action = _normalize_attr(action_attr)
        method_attr = form.get("method")
        method = _normalize_attr(method_attr).lower()

        if not action:
            action = (
                _normalize_attr(form.get("hx-post"))
                or _normalize_attr(form.get("hx-put"))
                or _normalize_attr(form.get("hx-patch"))
                or _normalize_attr(form.get("hx-delete"))
                or ""
            )

        if not method:
            if form.get("hx-post"):
                method = "post"
            elif form.get("hx-put"):
                method = "put"
            elif form.get("hx-patch"):
                method = "patch"
            elif form.get("hx-delete"):
                method = "delete"
            else:
                method = "get"

        # Build base data from all input fields in this form
        data = {}
        for input_elem in form.find_all("input"):
            name = input_elem.get("name")
            if name:
                value = input_elem.get("value", "")
                data[name] = value

        filled = self._form_data.get(form_selector or "form", {})
        for field_selector, value in filled.items():
            # Find the actual input name for that field selector
            field = form.select_one(field_selector)
            if field:
                name = field.get("name")
                if name:
                    data[name] = value

        # Perform the request
        if method == "post":
            enctype = form.get("enctype")
            hx_ext = form.get("hx-ext") or ""
            if enctype == "application/json" or "form-json" in hx_ext:
                self.post(action, json=data, **kwargs)
            else:
                self.post(action, data=data, **kwargs)
        elif method == "get":
            self.get(action, params=data, **kwargs)
        else:
            raise ValueError(f"Unsupported form method: {method}")

    def assert_status(self, status_code: int) -> None:
        assert self.response is not None, "No response loaded"
        assert self.response.status_code == status_code, f"Expected {status_code}, got {self.response.status_code}"

    def assert_contains(self, text: str, case_sensitive: bool = True) -> None:
        assert self.response is not None, "No response loaded"
        if not case_sensitive:
            text = text.lower()
            body = self.response.text.lower()
        else:
            body = self.response.text
        assert text in body, f"'{text}' not found in response"

    def assert_not_contains(self, text: str, case_sensitive: bool = True) -> None:
        assert self.response is not None, "No response loaded"
        if not case_sensitive:
            text = text.lower()
            body = self.response.text.lower()
        else:
            body = self.response.text
        assert text not in body, f"'{text}' found in response, but should not be"

    def assert_selector(self, selector: str, count: int | None = None) -> None:
        """
        Assert that a CSS selector matches exactly `count` elements.
        """

        elements = self.soup.select(selector) if self.soup else []
        if count is not None:
            assert len(elements) == count, f"Expected {count} elements, got {len(elements)}"
        else:
            assert elements, f"No elements found for selector: {selector}"

    def assert_title(self, title: str) -> None:
        """
        Assert that the page title equals `title`.
        """
        assert self.soup and self.soup.title, "No title tag found"
        assert self.soup.title.string == title, f"Expected title '{title}', got '{self.soup.title.string}'"

    @property
    def current_path(self) -> str | None:
        if not self.response:
            return None

        from urllib.parse import urlparse

        return urlparse(self.response.url).path
