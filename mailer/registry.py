from lib.logger import get_logger
from lib.mailer.base import Mailer
from lib.mailer.exceptions import MailerNotConfiguredError

logger = get_logger("mailer.registry")


class MailerRegistry:
    def __init__(self):
        self._mailer: "Mailer | None" = None

    def configure_mailer(self, mailer: "Mailer") -> "MailerRegistry":
        self._mailer = mailer
        logger.info(
            "Mailer configured: transport=%s from=%s",
            type(mailer._transport).__name__,
            mailer._from_email,
        )

        return self

    def get_mailer(self) -> "Mailer":
        if self._mailer is None:
            raise MailerNotConfiguredError("No mailer configured. Call mailer_registry.configure() at startup.")
        return self._mailer


mailer_registry = MailerRegistry()
