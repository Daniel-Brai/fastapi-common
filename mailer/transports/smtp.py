import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid

from lib.logger import get_logger
from lib.mailer.exceptions import MailerAuthError, MailerConnectionError, MailerError, MailerInvalidRecipientError
from lib.mailer.schemas import MailerResult
from lib.mailer.transports.base import AbstractTransport

logger = get_logger("lib.mailer.transports.smtp")


class SMTPTransport(AbstractTransport):
    """
    Standard SMTP transport.

    Examples:

        SMTPTransport(
            host     = "smtp.mailgun.org",
            port     = 587,
            username = "postmaster@mg.yourapp.com",
            password = "secret",
            use_tls  = True,    # STARTTLS on port 587
            use_ssl  = False,   # SSL on port 465, mutually exclusive with use_tls
            timeout  = 30,
        )
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout: int = 30,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl
        self._timeout = timeout

    def name(self) -> str:
        return "smtp"

    async def verify(self) -> bool:
        try:
            cls = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
            with cls(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls and not self._use_ssl:
                    smtp.starttls()

                if self._username and self._password:
                    smtp.login(self._username, self._password)

            return True
        except Exception as exc:
            logger.error("SMTPTransport: SMTP connectivity check failed: %s", exc)
            return False

    async def send(self, payload) -> MailerResult:
        msg = self._build_mime(payload)

        all_recipients = list(payload.recipients)
        if payload.cc:
            all_recipients.extend(payload.cc)
        if payload.bcc:
            all_recipients.extend(payload.bcc)

        try:
            result = self._smtp_send(msg, payload.sender, all_recipients)
            return MailerResult(
                transport=self.name(),
                message_id=msg["Message-ID"],
                status="sent",
                raw_response={"smtp_response": result},
            )
        except smtplib.SMTPRecipientsRefused as exc:
            logger.error("SMTPTransport: SMTP recipients refused: %s", exc.recipients)
            raise MailerInvalidRecipientError() from exc
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("SMTPTransport: SMTP auth error: %s", exc)
            raise MailerAuthError() from exc
        except smtplib.SMTPConnectError as exc:
            logger.error("SMTPTransport: SMTP connect error: %s", exc)
            raise MailerConnectionError() from exc
        except Exception as exc:
            logger.exception("SMTPTransport: SMTP send failed: %s", exc)
            raise MailerError("SMTPTransport: SMTP send failed") from exc

    def _smtp_send(self, msg: MIMEMultipart, sender: str, recipients: list[str]):
        cls = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP

        with cls(self._host, self._port, timeout=self._timeout) as smtp:
            if self._use_tls and not self._use_ssl:
                smtp.starttls()

            if self._username and self._password:
                smtp.login(self._username, self._password)

            return smtp.send_message(msg, from_addr=sender, to_addrs=recipients)

    def _build_mime(self, payload) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = payload.subject
        msg["From"] = payload.sender
        msg["To"] = ", ".join(payload.recipients)

        if payload.cc:
            msg["Cc"] = ", ".join(payload.cc)

        if payload.reply_to:
            msg["Reply-To"] = payload.reply_to

        domain = payload.sender.split("@")[-1].rstrip(">")
        msg["Message-ID"] = payload.message_id or make_msgid(domain=domain)

        if payload.text_content:
            msg.attach(MIMEText(payload.text_content, "plain", "utf-8"))
        if payload.html_content:
            msg.attach(MIMEText(payload.html_content, "html", "utf-8"))

        for att in payload.attachments:
            part = MIMEApplication(att.content)
            part.add_header("Content-Disposition", f'attachment; filename="{att.filename}"')
            part.add_header("Content-Type", att.content_type)
            msg.attach(part)

        return msg
