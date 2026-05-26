import re
from pathlib import Path
from typing import Any

from lib.logger import get_logger
from lib.mailer.exceptions import MailerTemplateError
from lib.mailer.schemas import MailerResult
from lib.mailer.transports.base import AbstractTransport

logger = get_logger("lib.mailer.transports.console")


class ConsoleTransport(AbstractTransport):
    """
    Console transport for development and testing.

    Prints the email content to stdout or routes through logging.

    Example:

        ConsoleTransport()                  # print() to stdout
        ConsoleTransport(use_logger=True)   # route through logging instead which uses the configured logger using the configure_logging
    """

    def __init__(self, *, use_logger: bool = False):
        self._use_logger = use_logger

    def name(self) -> str:
        return "console"

    def render_template(
        self,
        *,
        template: str,
        context: dict[str, Any] | None = None,
        templates_dir: str | Path | None = None,
    ) -> tuple[str | None, str | None, str]:
        if templates_dir is None:
            raise MailerTemplateError(
                "Cannot render console template emails: no templates_dir was configured. "
                "Pass templates_dir= to Mailer()."
            )

        template_name = self._text_template_name(template)
        template_path = Path(templates_dir) / template_name

        try:
            template_text = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MailerTemplateError(f"Failed to read console template {template_name!r}: {exc}") from exc

        try:
            rendered_text = template_text.format(**(context or {}))
        except (IndexError, KeyError, ValueError) as exc:
            raise MailerTemplateError(f"Failed to render console template {template_name!r}: {exc}") from exc

        return None, rendered_text, template_name

    async def send(self, payload) -> MailerResult:
        border = "─" * 64
        body = payload.text_content or (self._strip_html(payload.html_content) if payload.html_content else "(no body)")

        lines = [
            f"\n{border}",
            f"  MAILER — {self.name().upper()}",
            f"  From:    {payload.sender}",
            f"  To:      {', '.join(payload.recipients)}",
        ]
        if payload.cc:
            lines.append(f"  CC:      {', '.join(payload.cc)}")
        if payload.bcc:
            lines.append(f"  BCC:     {', '.join(payload.bcc)}")
        lines += [
            f"  Subject: {payload.subject}",
            f"  Tmpl:    {payload.template_name or '(inline)'}",
        ]
        if payload.attachments:
            att_summary = ", ".join(f"{a.filename} ({len(a.content):,}B)" for a in payload.attachments)
            lines.append(f"  Attach:  {att_summary}")
        lines += [border, body, f"{border}\n"]

        output = "\n".join(lines)
        if self._use_logger:
            logger.info(output)
        else:
            print(output)

        return MailerResult(
            transport=self.name(),
            message_id=payload.message_id,
            status="sent",
            raw_response={"detail": "Printed to console"},
        )

    def _strip_html(self, html: str) -> str:
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _text_template_name(template: str) -> str:
        if template.endswith(".mjml.html"):
            return f"{template.removesuffix('.mjml.html')}.txt"

        if template.endswith(".html"):
            return f"{template.removesuffix('.html')}.txt"

        if template.endswith(".txt"):
            return template

        return f"{template}.txt"
