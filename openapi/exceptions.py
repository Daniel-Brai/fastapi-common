class OpenAPIAuthError(Exception):
    """
    Base exception for OpenAPI-related authentication errors.
    """

    def __init__(self, status_code: int, message: str, headers: dict[str, str] | None = None):
        self.type = "openapi_error"
        self.status_code = status_code
        self.headers = headers or {}
        self.message = message

        super().__init__(f"OpenAPIAuthError: {message}")
