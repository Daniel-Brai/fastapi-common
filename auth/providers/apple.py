import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import jwt
from fastapi import Request, Response
from jwt import InvalidTokenError, PyJWKClient

from lib.auth.exceptions import OAuthError, OAuthStateMismatch
from lib.auth.providers.base import AbstractOAuthProvider
from lib.auth.providers.schemas import OAuthUserInfo
from lib.logger import get_logger

logger = get_logger("lib.auth.providers.apple")


_STATE_COOKIE = "apple_oauth_state"


class AppleProvider(AbstractOAuthProvider):
    """
    Apple Sign In provider.

    Apple differs from every other OAuth provider in two important ways:

    1. The client_secret is not a static string - you must generate a JWT
       signed with your Apple private key (ES256). It expires after at most
       6 months. This class regenerates it before each token exchange so you
       never have to rotate it manually.

    2. User profile information (name, email) is only included in the first
       authorization response. Subsequent logins only supply the `sub` (stable
       Apple user id) and optionally the email. Always persist the name on
       first login.

    Prerequisites (Apple Developer Console):
    - Create a Services ID (this becomes client_id, e.g. "com.yourapp.signin")
    - Enable "Sign in with Apple" and register your redirect URI
    - Create a private key (.p8 file); note the Key ID and your Team ID

    Note:
    Apple requires the redirect to be a POST, not a GET. The router handles
    this via a `response_mode=form_post` parameter - you need a POST endpoint
    at the callback URL.

    Attributes:

        client_id (str): Services ID from Apple Developer Console (e.g. "com.yourapp.signin")
        team_id (str): Your Apple Developer Team ID
        key_id (str): Key ID of the private key you created in Apple Developer Console
        private_key (str): PEM string of the .p8 private key you downloaded from Apple
        redirect_uri (str): The redirect URI you registered in Apple Developer Console
        scopes (list[str]): List of scopes to request (default: ["name", "email"])
        state_secret (str): Secret key for signing CSRF state tokens (default: random 32-byte hex string)
        secret_ttl (timedelta): TTL for the client_secret JWT (default: 180 days, max allowed by Apple)
        cookie_secure (bool): Whether the OAuth state cookie is marked `secure`.

    Examples:

        ```python
        configure_auth(
            backend,
            providers=[
                AppleProvider(
                    client_id="com.yourapp.signin",
                    team_id="XXXXXXXXXX",
                    key_id="XXXXXXXXXX",
                    private_key=open("AuthKey_XXXXXXXXXX.p8").read(),
                    redirect_uri="https://yourdomain.com/auth/oauth/apple/callback",
                )
            ],
        )
        ```
    """

    name = "apple"

    _AUTH_URL = "https://appleid.apple.com/auth/authorize"
    _TOKEN_URL = "https://appleid.apple.com/auth/token"
    _KEYS_URL = "https://appleid.apple.com/auth/keys"
    _ISSUER = "https://appleid.apple.com"

    def __init__(
        self,
        client_id: str,
        team_id: str,
        key_id: str,
        private_key: str,  # PEM string of the .p8 key
        redirect_uri: str,
        *,
        scopes: list[str] | None = None,
        state_secret: str | None = None,
        secret_ttl: timedelta = timedelta(days=180),  # Client secret JWT TTL Apple max is 6 months
        cookie_secure: bool = False,
    ):
        try:
            import jwt as _jwt  # noqa: F401
        except ImportError:
            raise ImportError("PyJWT is not installed. " "pip install 'pyjwt[crypto]'")
        try:
            import httpx as _httpx  # noqa: F401
        except ImportError:
            raise ImportError("httpx is not installed. pip install httpx")

        self._client_id = client_id
        self._team_id = team_id
        self._key_id = key_id
        self._private_key = private_key
        self._redirect_uri = redirect_uri
        self._scopes = scopes or ["name", "email"]
        self._state_secret = state_secret or secrets.token_hex(32)
        self._secret_ttl = secret_ttl
        self._cookie_secure = cookie_secure

    def _make_client_secret(self) -> str:
        """
        Generate a signed JWT to use as the client_secret for Apple token exchange.

        Apple requires this to be an ES256-signed JWT with:
            iss  — Team ID
            iat  — issued at
            exp  — expiry (≤ 6 months)
            aud  — "https://appleid.apple.com"
            sub  — Services ID (client_id)

        The JWT is signed with your .p8 private key.
        """

        now = int(datetime.now(timezone.utc).timestamp())
        claims = {
            "iss": self._team_id,
            "iat": now,
            "exp": now + int(self._secret_ttl.total_seconds()),
            "aud": self._ISSUER,
            "sub": self._client_id,
        }
        return jwt.encode(
            claims,
            self._private_key,
            algorithm="ES256",
            headers={"kid": self._key_id},
        )

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

        Apple requires response_mode=form_post for the callback.
        """

        state = self._make_state()
        signed = self._sign_state(state)

        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "response_mode": "form_post",  # Apple sends POST to your callback
            "scope": " ".join(self._scopes),
            "state": state,
        }
        return f"{self._AUTH_URL}?{urlencode(params)}", signed

    def handle_callback(self, request: Request) -> OAuthUserInfo:
        """
        Handle Apple's form_post callback.

        Apple POSTs to your callback with:
          • code  — authorization code
          • state — CSRF state
          • user  — JSON string with name/email (FIRST LOGIN ONLY)
          • id_token — signed JWT with claims (always present)

        For subsequent logins, `user` is absent — only `sub` (from id_token)
        and optionally `email` are available.
        """
        import json

        import httpx as http

        # Apple uses form_post; FastAPI exposes it as form data
        # We accept both form body and query params for flexibility
        form = {}
        try:
            # If called from a POST route with Form body
            form = dict(request.query_params)
        except Exception:
            pass

        code = form.get("code") or request.query_params.get("code")
        received_state = form.get("state") or request.query_params.get("state")
        id_token_raw = form.get("id_token") or request.query_params.get("id_token")
        user_json = form.get("user") or request.query_params.get("user")
        signed_cookie = request.cookies.get(_STATE_COOKIE, "")

        if not code:
            raise OAuthError("No authorization code in Apple callback")
        if not self._verify_state(signed_cookie, received_state):
            raise OAuthStateMismatch()

        # Exchange code for tokens
        client_secret = self._make_client_secret()
        token_resp = http.post(
            self._TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
            },
        )
        if not token_resp.is_success:
            raise OAuthError(f"Apple token exchange failed: {token_resp.text}")

        tokens = token_resp.json()
        id_token = tokens.get("id_token") or id_token_raw
        if not id_token:
            raise OAuthError("Apple did not return an id_token")

        # Decode id_token to extract claims (verify signature via Apple's JWKS)
        claims = self._decode_id_token(id_token)

        # Parse the user JSON if present (first login only)
        user_data: dict[str, Any] = {}
        if user_json:
            try:
                user_data = json.loads(user_json)
            except Exception:
                logger.warning("Failed to parse Apple user JSON: %s", user_json)

        name_data = user_data.get("name", {}) or {}
        given_name = name_data.get("firstName")
        family_name = name_data.get("lastName")
        full_name = " ".join(filter(None, [given_name, family_name])) or None

        email = claims.get("email") or user_data.get("email", "")

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        return OAuthUserInfo(
            provider=self.name,
            sub=claims["sub"],
            email=email,
            email_verified=claims.get("email_verified", False),
            name=full_name,
            given_name=given_name,
            family_name=family_name,
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            id_token=id_token,
            token_expires_at=expires_at,
            extra={
                "is_private_email": claims.get("is_private_email"),
                "real_user_status": claims.get("real_user_status"),
                "nonce_supported": claims.get("nonce_supported"),
            },
        )

    def _decode_id_token(self, id_token: str) -> dict:
        """
        Verify and decode the Apple id_token.

        Fetches Apple's JWKS on each call (production code should cache this).
        """
        jwk_client = PyJWKClient(self._KEYS_URL)

        try:
            signing_key = jwk_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=self._ISSUER,
            )
        except InvalidTokenError as exc:
            raise OAuthError(f"Apple id_token verification failed: {exc}") from exc

        return claims

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
