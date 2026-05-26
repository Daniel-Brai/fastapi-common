from lib.testing.database import MockAsyncSession, MockTransaction


class TransactionPatch:
    """
    Context manager for patching the transaction factory on a MockAsyncSession.
    """

    def __init__(self, session: MockAsyncSession) -> None:
        self._session = session

    def __call__(self) -> MockTransaction:
        tx = MockTransaction(self._session)
        self._session._last_transaction = tx
        return tx
