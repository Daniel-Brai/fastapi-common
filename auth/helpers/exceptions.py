from fastapi import HTTPException

from lib.auth.exceptions import AuthError


def auth_error_to_http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)
