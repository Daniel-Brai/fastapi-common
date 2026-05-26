import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import Request, Response

from lib.auth.exceptions import OAuthError, OAuthStateMismatch
from lib.auth.providers.base import AbstractOAuthProvider
from lib.auth.providers.schemas import OAuthUserInfo
from lib.logger import get_logger

logger = get_logger("lib.auth.providers.github")

_STATE_COOKIE = "github_oauth_state"


class GitHubProvider(AbstractOAuthProvider):
    """
    GitHub OAuth provider.

    Setup:
    1. Create an OAuth App in GitHub settings:
       https://github.com/settings/developers
    2. Add your callback URL:
       https://yourdomain.com/auth/oauth/github/callback

    Attributes:
        client_id (str): GitHub OAuth client ID.
        client_secret (str): GitHub OAuth client secret.
        redirect_uri (str): Registered OAuth callback URI.
        scopes (list[str]): Requested scopes (default: ["read:user", "user:email"]).
        state_secret (str): Secret used to sign CSRF state tokens.
        allow_signup (bool): Whether GitHub should show signup during auth.
        cookie_secure (bool): Whether the OAuth state cookie is marked `secure`.
    """

    name = "github"

    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USER_URL = "https://api.github.com/user"
    _EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        scopes: list[str] | None = None,
        state_secret: str | None = None,
        allow_signup: bool = True,
        cookie_secure: bool = False,
    ):
        try:
            import httpx as _httpx  # noqa: F401
        except ImportError:
            raise ImportError("httpx is not installed. pip install httpx")

        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes or ["read:user", "user:email"]
        self._state_secret = state_secret or secrets.token_hex(32)
        self._allow_signup = allow_signup
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
        state = self._make_state()
        signed = self._sign_state(state)

        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state,
            "allow_signup": "true" if self._allow_signup else "false",
        }
        return f"{self._AUTH_URL}?{urlencode(params)}", signed

    def handle_callback(self, request: Request) -> OAuthUserInfo:
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
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": self._redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if not token_resp.is_success:
            raise OAuthError(f"Token exchange failed: {token_resp.text}")

        tokens = token_resp.json()
        if "error" in tokens:
            error_description = tokens.get("error_description") or tokens.get("error")
            raise OAuthError(f"Token exchange failed: {error_description}")

        access_token = tokens.get("access_token")
        if not access_token:
            raise OAuthError("GitHub did not return an access_token")

        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        profile_resp = http.get(self._USER_URL, headers=auth_headers)
        if not profile_resp.is_success:
            raise OAuthError(f"User profile fetch failed: {profile_resp.text}")

        profile = profile_resp.json()

        email = profile.get("email")
        email_verified = False

        emails_resp = http.get(self._EMAILS_URL, headers=auth_headers)
        if emails_resp.is_success:
            emails_data = emails_resp.json()
            if isinstance(emails_data, list):
                primary = next((e for e in emails_data if e.get("primary")), None)
                verified = next((e for e in emails_data if e.get("verified")), None)
                selected = primary or verified
                if selected:
                    email = selected.get("email") or email
                    email_verified = bool(selected.get("verified", False))
        else:
            logger.warning("GitHub email lookup failed: %s", emails_resp.text)

        expires_at = None
        expires_in = tokens.get("expires_in")
        if isinstance(expires_in, int):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return OAuthUserInfo(
            provider=self.name,
            sub=str(profile["id"]),
            email=email or "",
            email_verified=email_verified,
            name=profile.get("name") or profile.get("login"),
            given_name=None,
            family_name=None,
            picture=profile.get("avatar_url"),
            locale=None,
            access_token=access_token,
            refresh_token=tokens.get("refresh_token"),
            id_token=None,
            token_expires_at=expires_at,
            extra={
                k: v
                for k, v in profile.items()
                if k
                not in {
                    "id",
                    "email",
                    "name",
                    "login",
                    "avatar_url",
                }
            },
        )

    def set_state_cookie(self, response: Response, signed_state: str) -> None:
        response.set_cookie(
            key=_STATE_COOKIE,
            value=signed_state,
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=self._cookie_secure,
        )

    @staticmethod
    def clear_state_cookie(response: Response) -> None:
        response.delete_cookie(_STATE_COOKIE)
