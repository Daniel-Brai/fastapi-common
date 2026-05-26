from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import EmailStr
from sqlmodel import select

from lib.auth.helpers.db import db_commit, db_exec, db_get, db_refresh, db_session
from lib.auth.models import OAuthAccount


async def user_by_email(email: str | EmailStr) -> Any | None:
    """
    Fetch a user by email. Returns None if not found.
    """

    from lib.auth.config import get_user_model

    UserModel = get_user_model()

    async with db_session() as s:
        result = await db_exec(s, select(UserModel).where(UserModel.email == email))
        return result.first()


async def create_user(user: dict[str, Any], raise_exceptions: bool = False) -> Any:
    """
    Create a new user record with authorization defaults.

    If a user already exists for the provided email, this returns None unless
    raise_exceptions is True.
    """

    from lib.auth.config import get_authorization_defaults, get_hasher, get_user_model

    UserModel = get_user_model()

    async with db_session() as s:
        _r = await db_exec(s, select(UserModel).where(UserModel.email == user["email"]))

        existing = _r.first()
        if existing:
            if raise_exceptions:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

            return existing

        plain_password = user.pop("password", None)

        if plain_password is None:
            raise ValueError("Password is required to create a user. " "Include 'password' in the user dict.")

        user_attrs: dict[str, Any] = {
            "email": user["email"],
        }

        user_attrs.update(get_authorization_defaults(UserModel))

        model_fields = getattr(UserModel, "model_fields", {})
        if "roles" in user and "roles" in model_fields:
            user_attrs["roles"] = user["roles"]
        elif "roles" not in user_attrs and "roles" in model_fields:
            user_attrs["roles"] = []

        user_attrs.update({k: v for k, v in user.items() if k not in ("email", "roles")})

        user = UserModel(**user_attrs)  # type: ignore[arg-type]

        if plain_password is not None:
            user.hashed_password = get_hasher().hash(plain_password, user.password_salt)  # type: ignore[assignment]

        s.add(user)
        await db_commit(s)
        await db_refresh(s, user)
        return user


async def create_users(
    users: list[dict[str, Any]],
    raise_exceptions: bool = False,
) -> list[Any]:
    """
    Create multiple users in a single batch.

    This performs a single DB lookup for existing emails and inserts all new
    users in one transaction. It does not call :func:`create_user`.
    """

    from lib.auth.config import get_authorization_defaults, get_hasher, get_user_model

    if not isinstance(users, list):
        raise TypeError("users must be a list of user dicts")

    UserModel = get_user_model()

    emails: list[str] = []
    duplicate_emails: set[str] = set()
    seen_emails: set[str] = set()

    for user in users:
        if "email" not in user:
            raise ValueError("Each user dict must include an 'email' key.")

        email = user["email"]
        emails.append(email)

        if email in seen_emails:
            duplicate_emails.add(email)
        else:
            seen_emails.add(email)

    if duplicate_emails:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate email(s) found in batch input: " + ", ".join(sorted(duplicate_emails))),
        )

    async with db_session() as s:
        if emails:
            existing_result = await db_exec(
                s,
                select(UserModel).where(UserModel.email.in_(tuple(emails))),  # type: ignore[attr-defined]
            )
            existing_by_email = {existing.email: existing for existing in existing_result.all()}
        else:
            existing_by_email = {}

        created_users: list[Any] = []

        for user in users:
            email = user["email"]
            existing_user = existing_by_email.get(email)
            if existing_user:
                if raise_exceptions:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Email already registered: {email}",
                    )

                created_users.append(existing_user)
                continue

            user_data = dict(user)
            plain_password = user_data.pop("password", None)
            if plain_password is None:
                raise ValueError("Password is required to create a user. " "Include 'password' in each user dict.")

            user_attrs: dict[str, Any] = {
                "email": email,
            }
            user_attrs.update(get_authorization_defaults(UserModel))

            model_fields = getattr(UserModel, "model_fields", {})
            if "roles" in user_data and "roles" in model_fields:
                user_attrs["roles"] = user_data["roles"]
            elif "roles" not in user_attrs and "roles" in model_fields:
                user_attrs["roles"] = []

            user_attrs.update({k: v for k, v in user_data.items() if k not in ("email", "roles")})

            new_user = UserModel(**user_attrs)  # type: ignore[arg-type]
            new_user.hashed_password = get_hasher().hash(
                plain_password, new_user.password_salt
            )  # type: ignore[assignment]

            s.add(new_user)
            created_users.append(new_user)

        await db_commit(s)

        for user_obj in created_users:
            await db_refresh(s, user_obj)

        return created_users


async def find_or_create_oauth_user(
    provider: str,
    sub: str,
    email: str,
    email_verified: bool = False,
    name: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    id_token: str | None = None,
    token_expires_at=None,
    extra: dict | None = None,
):
    """
    Find an existing OAuthAccount → User, or create both if first login.

    Also handles account linking: if a UserRecord with the same email exists,

    link the OAuth account to it (same user, different login method).
    """

    from lib.auth.config import get_authorization_defaults, get_user_model

    extra = extra or {}
    async with db_session() as s:
        _r = await db_exec(
            s,
            select(OAuthAccount).where(OAuthAccount.provider == provider).where(OAuthAccount.provider_sub == sub),
        )

        oauth_acc = _r.first()

        if oauth_acc:
            oauth_acc.access_token = access_token
            oauth_acc.refresh_token = refresh_token
            oauth_acc.id_token = id_token
            oauth_acc.token_expires_at = token_expires_at
            oauth_acc.updated_at = datetime.now()
            s.add(oauth_acc)
            user = await db_get(s, get_user_model(), oauth_acc.user_id)
            await db_commit(s)
            await db_refresh(s, user)
            return user

        _r = await db_exec(s, select(get_user_model()).where(get_user_model().email == email))

        user = _r.first()

        if not user:
            UserModel = get_user_model()
            user_attrs: dict[str, Any] = {
                "email": email,
                "email_verified": email_verified,
            }
            user_attrs.update(get_authorization_defaults(UserModel))

            # Preserve previous behavior: initialize roles when the model supports it.
            model_fields = getattr(UserModel, "model_fields", {})
            if "roles" not in user_attrs and "roles" in model_fields:
                user_attrs["roles"] = []

            user = UserModel(**user_attrs)  # type: ignore[arg-type]

            if getattr(user, "name", None) is not None and name is not None:
                user.name = name  # type: ignore[assignment]

            if getattr(user, "last_login_at", None) is not None:
                user.last_login_at = datetime.now()  # type: ignore[assignment]

            s.add(user)
            s.flush()

        oauth_acc = OAuthAccount(  # type: ignore[assignment]
            user_id=user.id,
            provider=provider,
            provider_sub=sub,
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            token_expires_at=token_expires_at,
            extra=extra,
        )
        s.add(oauth_acc)
        await db_commit(s)
        await db_refresh(s, user)
        return user
