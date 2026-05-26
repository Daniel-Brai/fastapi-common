from fastapi import status


class ServiceError(Exception):
    """
    Base exception for service errors
    """

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.type = "service_error"
        self.message = message
        self.status_code = status_code

        super().__init__(message)
