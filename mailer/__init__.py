from .base import Mailer
from .config import configure_mailer, get_mailer
from .exceptions import MailerError
from .schemas import Attachment, MailerPayload, MailerResult, ResolvedAttachment
from .transports import ConsoleTransport, SESTransport, SMTPTransport

__all__ = [
    "configure_mailer",
    "get_mailer",
    "Mailer",
    "Attachment",
    "ResolvedAttachment",
    "MailerPayload",
    "MailerResult",
    "MailerError",
    "ConsoleTransport",
    "SMTPTransport",
    "SESTransport",
]
