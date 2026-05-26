from abc import ABC, abstractmethod

from fastapi import Request

from lib.auth.providers.schemas import OAuthUserInfo


class AbstractOAuthProvider(ABC):
    """
    Base class for OAuth providers.

    To add a new provider, subclass this and implement the abstract methods.

    Examples:

        class MicrosoftProvider(AbstractOAuthProvider):
            name = "microsoft"

            def get_redirect_url(self, request: Request) -> tuple[str, str]: ...
            def handle_callback(self, request: Request) -> OAuthUserInfo: ...
    """

    name: str  # unique slug used in URL paths: /oauth/{name}/redirect

    @abstractmethod
    def get_redirect_url(self, request: Request) -> tuple[str, str]:
        """
        Build and return (authorization_url, signed_state).

        You must embed a CSRF state value, store it in a signed cookie or `FastAPI`'s SessionMiddleware so handle_callback can verify it.
        """
        ...

    @abstractmethod
    def handle_callback(self, request: Request) -> OAuthUserInfo:
        """
        Complete the OAuth exchange:
          • Verify state (raise OAuthStateMismatch on failure)
          • Exchange code for tokens
          • Fetch / decode user profile
          • Return OAuthUserInfo
        """
        ...
