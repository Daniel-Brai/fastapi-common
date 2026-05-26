import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode

from fastapi import Request, Response

from lib.auth.exceptions import OAuthError, OAuthStateMismatch
from lib.auth.providers.base import AbstractOAuthProvider
from lib.auth.providers.schemas import OAuthUserInfo
from lib.logger import get_logger

logger = get_logger("lib.auth.providers.google")

_STATE_COOKIE = "oauth_state"


class GoogleProvider(AbstractOAuthProvider):
    """
    Google OAuth 2.0 provider.

    Setup:
    1. Create a Google Cloud project and OAuth 2.0 credentials
       (https://console.cloud.google.com/apis/credentials).
    2. Add your redirect URI:
       https://yourdomain.com/auth/oauth/google/callback

    CSRF state is stored in a signed cookie, so there is no
    server-side state and no SessionMiddleware dependency.

    Attributes:
        client_id (str): Google OAuth client ID.
        client_secret (str): Google OAuth client secret.
        redirect_uri (str): Registered OAuth callback URI.
        scopes (list[str]): Requested scopes (defaults to openid, email, profile).
        state_secret (str): Secret used to sign CSRF state tokens.
        prompt (Literal["select_account", "consent"] | None): Optional Google prompt value.
        access_type (str): OAuth access type, usually "offline" for refresh tokens.
        cookie_secure (bool): Whether the OAuth state cookie is marked `secure`.

    Examples:

        ```python
        configure_auth(
            backend,
            providers=[
                GoogleProvider(
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET,
                    redirect_uri="https://yourdomain.com/auth/oauth/google/callback",
                )
            ],
        )
        ```
    """

    name = "google"

    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        scopes: list[str] | None = None,
        state_secret: str | None = None,
        prompt: Literal["select_account", "consent"] | None = None,
        access_type: str = "offline",  # "offline" to get refresh_token
        cookie_secure: bool = False,
    ):
        try:
            import httpx as _httpx  # noqa: F401
        except ImportError:
            raise ImportError("httpx is not installed. pip install httpx")

        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes or ["openid", "email", "profile"]
        self._state_secret = state_secret or secrets.token_hex(32)
        self._prompt = prompt
        self._access_type = access_type
        self._cookie_secure = cookie_secure

    def _make_state(self) -> str:
        return secrets.token_urlsafe(32)

    def _sign_state(self, state: str) -> str:
        sig = hmac.new(self._state_secret.encode(), state.encode(), hashlib.sha256).hexdigest()
        return f"{state}.{sig}"

    def _verify_state(self, signed: str, received: str | None) -> bool:
        try:
            token, sig = signed.rsplit(".", 1)
            expected = hmac.new(self._state_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(sig, expected) and token == received
        except Exception:
            return False

    def get_redirect_url(self, request: Request) -> tuple[str, str]:
        """
        Returns (authorization_url, signed_state).

        The router stores signed_state in a cookie, then redirects to authorization_url.
        """

        state = self._make_state()
        signed = self._sign_state(state)

        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state,
            "access_type": self._access_type,
        }
        if self._prompt:
            params["prompt"] = self._prompt

        url = f"{self._AUTH_URL}?{urlencode(params)}"
        return url, signed

    def handle_callback(self, request: Request) -> OAuthUserInfo:
        """
        Complete the Google OAuth exchange.

        Expects:
          • request.query_params["code"]  — authorization code
          • request.query_params["state"] — CSRF state to verify against cookie
          • request.cookies[_STATE_COOKIE] — signed state stored during redirect
        """

        import httpx as http

        code = request.query_params.get("code")
        received_state = request.query_params.get("state")
        signed_cookie = request.cookies.get(_STATE_COOKIE, "")

        if not code:
            raise OAuthError("No authorization code in callback")
        if not self._verify_state(signed_cookie, received_state):
            raise OAuthStateMismatch()

        token_resp = http.post(
            self._TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if not token_resp.is_success:
            raise OAuthError(f"Token exchange failed: {token_resp.text}")

        tokens = token_resp.json()

        info_resp = http.get(
            self._INFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if not info_resp.is_success:
            raise OAuthError(f"User info fetch failed: {info_resp.text}")

        profile = info_resp.json()

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        return OAuthUserInfo(
            provider=self.name,
            sub=profile["sub"],
            email=profile.get("email", ""),
            email_verified=profile.get("email_verified", False),
            name=profile.get("name"),
            given_name=profile.get("given_name"),
            family_name=profile.get("family_name"),
            picture=profile.get("picture"),
            locale=profile.get("locale"),
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            id_token=tokens.get("id_token"),
            token_expires_at=expires_at,
            extra={
                k: v
                for k, v in profile.items()
                if k
                not in {
                    "sub",
                    "email",
                    "email_verified",
                    "name",
                    "given_name",
                    "family_name",
                    "picture",
                    "locale",
                }
            },
        )

    def set_state_cookie(self, response: Response, signed_state: str) -> None:
        response.set_cookie(
            key=_STATE_COOKIE,
            value=signed_state,
            max_age=600,  # 10 min enough for the OAuth round-trip
            httponly=True,
            samesite="lax",
            secure=self._cookie_secure,
        )

    @staticmethod
    def clear_state_cookie(response: Response) -> None:
        response.delete_cookie(_STATE_COOKIE)
