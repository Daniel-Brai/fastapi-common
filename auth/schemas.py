from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, EmailStr, StringConstraints

from lib.auth.token import TokenPair
from lib.auth.types import Password
from lib.auth.user import AuthUserMixin


class AuthRegisterRequest(BaseModel):
    """
    Schema for user registration request.

    Attributes:
        email (EmailStr): User's email address.
        password (Password): User's password.
        name (str | None): Optional name of the user.
    """

    name: str | None = None
    email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]
    password: Password


class AuthLoginRequest(BaseModel):
    """
    Schema for user login request.

    Attributes:
        email (EmailStr): User's email address.
        password (Password): User's password.
    """

    email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]
    password: Password


class AuthUserResponse(BaseModel):
    """
    Schema for user output.

    Attributes:
        name (str | None): Optional name of the user.
        email (str): User's email address.
        email_verified (bool): Whether the user's email is verified.
        roles (list[str]): List of roles assigned to the user.
        created_at (datetime): Timestamp of when the user was created.
        last_login_at (datetime | None): Timestamp of the user's last login.
    """

    name: str | None = None
    email: str
    email_verified: bool
    roles: list[str]
    created_at: datetime
    last_login_at: datetime | None = None

    @classmethod
    def from_user(cls, user: AuthUserMixin | Any) -> "AuthUserResponse":
        return cls(
            name=getattr(user, "name", None),
            email=user.email,
            email_verified=user.email_verified,
            roles=user.roles,
            created_at=user.created_at,
            last_login_at=getattr(user, "last_login_at", None),
        )


class AuthRecoverAccountRequest(BaseModel):
    """
    Schema for recover account request.

    Attributes:
        email (EmailStr): User's email address.
    """

    email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]


class AuthChangePasswordRequest(BaseModel):
    """
    Schema for change password request.

    Attributes:
        current_password (Password): User's current password.
        new_password (Password): User's new password.
    """

    current_password: Password
    new_password: Password


class AuthChangeEmailRequest(BaseModel):
    """
    Schema for change email request.

    Attributes:
        new_email (EmailStr): User's new email address.
        current_password (Password | None): User's current password, required for password-based accounts.
    """

    new_email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]
    current_password: Password | None = None  # required for password-based accounts


class AuthForgotPasswordRequest(BaseModel):
    """
    Schema for forgot password request.

    Attributes:
        email (EmailStr): User's email address.
    """

    email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]


class AuthResetPasswordRequest(BaseModel):
    """
    Schema for reset password request.

    Attributes:
        token (str): Password reset token.
        password (Password): User's new password.
    """

    token: str
    password: Password


class AuthMagicLinkRequest(BaseModel):
    """
    Schema for magic link request.

    Attributes:
        email (EmailStr): User's email address.
    """

    email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]


class AuthSendVerificationEmailRequest(BaseModel):
    """
    Schema for sending a verification email manually.

    Attributes:
        email (EmailStr): User's email address.
    """

    email: Annotated[EmailStr, StringConstraints(strip_whitespace=True, to_lower=True)]


class AuthSessionTokenResponse(BaseModel):
    """
    Schema for authentication response containing only the token if available.

    Attributes:
        token (TokenPair | None): The authentication token.
    """

    token: TokenPair | None = None


class AuthSessionResponse(AuthSessionTokenResponse):
    """
    Schema for authentication response containing user info and optional token.

    Attributes:
        user (AuthUserResponse): The authenticated user.
        token (TokenPair | None): The authentication token.
    """

    user: AuthUserResponse
