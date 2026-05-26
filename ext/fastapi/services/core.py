from typing import Any

from lib.database import AsyncSession
from lib.database.transaction import Transaction
from lib.logger import LoggerService


class BaseService(LoggerService):
    """
    Base service class providing common functionality for all services.

    This class can be extended by other service classes to inherit common functionality, such as logging and database access.
    """

    def __init__(self) -> None:
        super().__init__()


class Service(BaseService):
    """
    Service class providing common functionality for all services that require database access.

    It also provides a context manager for handling database transactions, ensuring that operations are executed within a transactional scope.

    Example usage:

        class MyService(Service):

            def __init__(self, db: AsyncSession):
                super().__init__(db)

                self.repo = MyRepository(db)

            async def perform_operation(self):
                async with self.transaction():
                    # All database operations here will be part of the same transaction
                    ...
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    def transaction(self) -> Transaction:
        """
        Context manager for database transactions

        Example:

            async with self.transaction():
                # perform database operations using transaction context
        """

        return Transaction(self.db)


class RunnableService(BaseService):
    """
    Base class for services that need to be run as background tasks.

    This class should be used when the runnable operation does not require an ``AsyncSession``.
    """

    async def run(self, *args: Any, **kwargs: Any):
        """
        Method to be implemented by subclasses to define the service's main logic.

        This method will be called when the service is run as a background task.
        """
        raise NotImplementedError("Subclasses must implement the run() method.")


class IORunnableService(RunnableService):
    """
    Base class for services that need to be run as background tasks and also
    require database access.

    This class should be used when the runnable operation touches the DB and
    therefore needs an ``AsyncSession`` to be provided to the constructor.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()

        self.db = db

    async def run(self, *args: Any, **kwargs: Any):
        """
        Method to be implemented by subclasses to define the service's main logic.

        This method will be called when the service is run as a background task.
        """
        raise NotImplementedError("Subclasses must implement the run() method.")


class StandaloneRunnableService(RunnableService):
    """
    Base class for services that need to be run as background tasks but do not
    require database access.

    Use this when the runnable operation does not require an ``AsyncSession``.
    """

    def __init__(self) -> None:
        super().__init__()

    async def run(self, *args: Any, **kwargs: Any):
        """
        Method to be implemented by subclasses to define the service's main logic.

        This method will be called when the service is run as a background task.
        """
        raise NotImplementedError("Subclasses must implement the run() method.")
