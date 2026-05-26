import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError

from lib.logger import get_logger

logger = get_logger("lib.auth.token")


@dataclass
class AccessTokenClaims:
    """
    Claims embedded in the access JWT.

    Attributes:

        sub (str): user UUID (string)
        email (str): user email
        roles (list[str]): list of role strings
        jti (str): unique token id (for future revocation lists)
        iat (int | None): issued-at (UTC epoch seconds)
        exp (int | None): expiry (UTC epoch seconds)
    """

    sub: str
    email: str
    roles: list[str]
    jti: str = field(default_factory=lambda: str(uuid.uuid4()))
    iat: int | None = None
    exp: int | None = None

    def as_dict(self) -> dict:
        return {
            "sub": self.sub,
            "email": self.email,
            "roles": self.roles,
            "jti": self.jti,
            "iat": self.iat,
            "exp": self.exp,
            "typ": "access",
        }


@dataclass
class RefreshTokenClaims:
    """
    Claims embedded in the refresh JWT.

    Attributes:
        sub (str): user UUID
        jti (str): this token's DB token_id
        fid (str): rotation family_id
        iat (int | None): issued-at (UTC epoch seconds)
        exp (int | None): expiry (UTC epoch seconds)
    """

    sub: str
    jti: str = field(default_factory=lambda: str(uuid.uuid4()))
    fid: str = field(default_factory=lambda: str(uuid.uuid4()))
    iat: int | None = None
    exp: int | None = None

    def as_dict(self) -> dict:
        return {
            "sub": self.sub,
            "jti": self.jti,
            "fid": self.fid,
            "iat": self.iat,
            "exp": self.exp,
            "typ": "refresh",
        }


@dataclass
class TokenPair:
    """
    Represents a pair of access and refresh tokens, along with metadata for the client.

    Attributes:

        access_token (str): Bearer token for Authorization header
        refresh_token (str): opaque JWT; deliver via httpOnly cookie or response body
        token_type (str): always "bearer"
        expires_in (int): access token TTL in seconds (Default: 900, i.e. 15 minutes)
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 min default


class TokenCodec:
    """
    Thin wrapper around pyjwt for encode/decode.

    Supports both symmetric (HS256) and asymmetric (RS256) algorithms.

    Examples:

        symmetric  — codec = TokenCodec(secret="...", algorithm="HS256")
        asymmetric — codec = TokenCodec(
                         private_key=rsa_pem,
                         public_key=rsa_pem,
                         algorithm="RS256",
                     )
    """

    def __init__(
        self,
        *,
        secret: str | None = None,
        private_key: str | None = None,
        public_key: str | None = None,
        algorithm: str = "HS256",
    ):
        if algorithm.startswith("HS"):
            if not secret:
                raise ValueError("HS* algorithms require `secret`")

            self._sign_key = secret
            self._verify_key = secret
        else:
            if not (private_key and public_key):
                raise ValueError("RS*/ES* algorithms require `private_key` and `public_key`")

            self._sign_key = private_key
            self._verify_key = public_key

        self._algorithm = algorithm

    def encode(self, claims: dict) -> str:
        return jwt.encode(claims, self._sign_key, algorithm=self._algorithm)

    def decode(self, token: str) -> dict:
        """
        Raises jwt.InvalidTokenError on invalid / expired token.
        """
        return jwt.decode(token, self._verify_key, algorithms=[self._algorithm])

    def make_access_token(self, claims: AccessTokenClaims, ttl: timedelta) -> str:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        claims.iat = now
        claims.exp = now + int(ttl.total_seconds())
        return self.encode(claims.as_dict())

    def make_refresh_token(self, claims: RefreshTokenClaims, ttl: timedelta) -> str:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        claims.iat = now
        claims.exp = now + int(ttl.total_seconds())
        return self.encode(claims.as_dict())

    def decode_access(self, token: str) -> AccessTokenClaims:
        data = self.decode(token)

        if data.get("typ") != "access":
            raise InvalidTokenError("Token is not an access token")

        return AccessTokenClaims(
            sub=data["sub"],
            email=data["email"],
            roles=data.get("roles", []),
            jti=data["jti"],
            iat=data.get("iat"),
            exp=data.get("exp"),
        )

    def decode_refresh(self, token: str) -> RefreshTokenClaims:
        data = self.decode(token)

        if data.get("typ") != "refresh":
            raise InvalidTokenError("Token is not a refresh token")

        return RefreshTokenClaims(
            sub=data["sub"],
            jti=data["jti"],
            fid=data["fid"],
            iat=data.get("iat"),
            exp=data.get("exp"),
        )
