from lib.mailer.base import Mailer
from lib.mailer.registry import MailerRegistry, mailer_registry


def configure_mailer(mailer: Mailer) -> MailerRegistry:
    """
    Register the Mailer instance. Call once at application startup.

    Examples:

        configure_mailer(
            Mailer(transport=SmtpTransport(...), from_email="noreply@example.com")
        )
    """
    return mailer_registry.configure_mailer(mailer)


def get_mailer() -> Mailer:
    """
    Get the configured Mailer instance.

    Raises:
        MailerNotConfiguredError: If no mailer has been configured yet.
    """
    return mailer_registry.get_mailer()
