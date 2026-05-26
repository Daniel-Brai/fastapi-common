from lib.logger import get_logger


class LoggerService:
    """
    Service for managing application logging.
    """

    def __init__(self):
        self.logger = get_logger(f"{self.__class__.__module__}.{self.__class__.__qualname__}")
