from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Request, Response

from lib.auth.user import AuthUserMixin


class AbstractBackend(ABC):
    """
    Base class for auth backends.

    Subclasses must implement the abstract methods.
    """

    @property
    def _engine(self) -> Any:
        from lib.auth.registry import auth_registry

        return auth_registry.db_engine

    @property
    def _user_model(self) -> type[AuthUserMixin]:
        from lib.auth.registry import auth_registry

        return auth_registry.user_model_class

    @property
    def _is_async(self) -> bool:
        from lib.auth.registry import auth_registry

        return auth_registry.is_async

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[Any]:
        """
        Yield a DB session appropriate for the configured engine type.

        Always use 'async with':

            async with self._session() as s:
                result = await self._exec(s, select(User).where(...))
        """

        engine = self._engine
        if self._is_async:
            from sqlmodel.ext.asyncio.session import AsyncSession

            async with AsyncSession(engine, expire_on_commit=False) as s:
                yield s
        else:
            from sqlalchemy.orm import Session

            with Session(engine) as s:
                yield s

    async def _exec(self, session: Any, stmt: Any) -> Any:
        """
        Execute a select, awaiting when session is async.
        """
        if self._is_async:
            return await session.exec(stmt)

        return session.exec(stmt)

    async def _get(self, session: Any, model: type, pk: Any) -> Any:
        """
        Get by PK, awaiting when session is async.
        """
        if self._is_async:
            return await session.get(model, pk)

        return session.get(model, pk)

    async def _commit(self, session: Any) -> None:
        """
        Commit, awaiting when session is async.
        """
        if self._is_async:
            await session.commit()
        else:
            session.commit()

    async def _refresh(self, session: Any, obj: Any) -> None:
        """
        Refresh an ORM object from the DB, awaiting when async.
        """
        if self._is_async:
            await session.refresh(obj)
        else:
            session.refresh(obj)

    async def _add_commit_refresh(self, session: Any, obj: Any) -> Any:
        """
        Add, commit, and refresh.
        """
        session.add(obj)
        await self._commit(session)
        await self._refresh(session, obj)
        return obj

    @property
    def name(self) -> str:
        """
        Return a short name for the backend type, e.g "jwt", "db", etc. Used in logs and error messages.
        """
        return type(self).__name__.lower().removesuffix("backend")

    @abstractmethod
    def auto_login(self) -> bool:
        """
        Whether to automatically log in the user after registration or password reset.

        Defaults to True. Can be overridden by backends that want to disable auto-login.
        """
        return True

    @abstractmethod
    async def login(
        self,
        user: Any,
        request: Request,
        response: Response | None,
        attach: bool = True,
    ) -> Any:
        """
        Issue credentials after a successful authentication.

        Return value is backend-specific (TokenPair / Session).
        """
        ...

    @abstractmethod
    async def logout(self, request: Request, response: Response) -> None:
        """
        Revoke the current session / refresh-token family.
        """
        ...

    async def refresh(self, request: Request, response: Response | None, attach: bool = True) -> Any:
        """
        Rotate the refresh token.
        """
        raise NotImplementedError(f"{self.name} backend does not implement refresh")

    @abstractmethod
    async def authenticate(self, credential: Any | None) -> Any:
        """
        Extract and validate the credential from the incoming Request.

        Returns the user model instance on success.

        Raises an AuthError subclass on failure.
        """
        ...

    @abstractmethod
    def attach(self, credential: Any, response: Response) -> None:
        """
        Write the issued credential to the Response. No-op by default.
        """

    async def sweep(self) -> int:
        """
        Delete expired DB rows. Returns the number deleted.
        """
        return 0
