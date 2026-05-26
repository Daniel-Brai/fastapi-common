class AuthError(Exception):
    """
    Base for all auth library exceptions.
    """

    status_code: int = 401
    detail: str = "Authentication error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class AuthConfigError(AuthError):
    status_code = 500
    detail = "Authentication service is not available"


class NotAuthenticated(AuthError):
    status_code = 401
    detail = "Not authenticated"


class InvalidCredentials(AuthError):
    status_code = 401
    detail = "Invalid credentials"


class TokenExpired(AuthError):
    status_code = 401
    detail = "Token has expired. Please log in again."


class TokenInvalid(AuthError):
    status_code = 401
    detail = "Token is invalid. Please log in again."


class TokenRevoked(AuthError):
    status_code = 401
    detail = "Token has been revoked. Please log in again."


class RefreshTokenReuse(AuthError):
    """
    Raised when a refresh token that was already rotated is presented again.

    The entire token family is invalidated (theft detection).
    """

    status_code = 401
    detail = "Refresh token reuse detected, all sessions invalidated"


class AccountScheduledForDeletion(AuthError):
    status_code = 403
    detail = "Account is scheduled for deletion"


class InactiveUser(AuthError):
    status_code = 403
    detail = "Account is inactive"


class PermissionDenied(AuthError):
    status_code = 403
    detail = "Permission denied"


class OAuthError(AuthError):
    status_code = 400
    detail = "OAuth error"


class OAuthStateMismatch(OAuthError):
    detail = "OAuth state parameter mismatch"


class UserNotFound(AuthError):
    status_code = 404
    detail = "Account not found. Please sign up to continue."


class EmailNotVerified(AuthError):
    status_code = 403
    detail = "Email address is not verified"


class EmailAlreadyVerified(AuthError):
    status_code = 400
    detail = "Email address is already verified"
