from sqlalchemy.orm import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.logger import get_logger

logger = get_logger(__name__)


class Transaction:
    """
    Transaction context helper for SQLAlchemy ``Session`` and ``AsyncSession``.

    The helper starts/controls commit and rollback only when there is no active
    transaction on the provided session. This makes it safe to use inside code
    that may already be running in a higher-level transaction boundary.
    """

    def __init__(self, session: Session | AsyncSession):
        self.session = session
        self._should_manage = not session.in_transaction()

    def __enter__(self) -> Session:
        if isinstance(self.session, AsyncSession):
            raise TypeError("Use 'async with Transaction(async_session)' for AsyncSession")

        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:
        if isinstance(self.session, AsyncSession):
            raise TypeError("Use 'async with Transaction(async_session)' for AsyncSession")

        if not self._should_manage:
            return False

        if exc is not None:
            self.session.rollback()
            logger.error(f"Transaction failed, rolling back: {exc}", exc_info=exc)
            return False

        self.session.commit()
        return False

    async def __aenter__(self) -> Session | AsyncSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if isinstance(self.session, AsyncSession):
            if not self._should_manage:
                return False

            if exc is not None:
                await self.session.rollback()
                logger.error(f"Transaction failed, rolling back: {exc}", exc_info=exc)
                return False

            await self.session.commit()
            return False

        if not self._should_manage:
            return False

        if exc is not None:
            self.session.rollback()
            logger.error(f"Transaction failed, rolling back: {exc}", exc_info=exc)
            return False

        self.session.commit()
        return False
