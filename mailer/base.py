import asyncio
from pathlib import Path
from typing import Any

from lib.logger import get_logger
from lib.mailer.environment import MjmlTemplateEnvironment
from lib.mailer.exceptions import MailerTemplateError
from lib.mailer.schemas import (
    Attachment,
    MailerPayload,
    MailerResult,
    MailerTemplateMessage,
    ResolvedAttachment,
    ResolvedMailerPayload,
)
from lib.mailer.transports import AbstractTransport

logger = get_logger("lib.mailer.base")


class Mailer:
    """
    Mailer is the main interface for sending emails.

    It manages a transport and an optional MJML template environment.
    """

    def __init__(
        self,
        transport: AbstractTransport,
        *,
        from_email: str,
        from_name: str,
        templates_dir: str | Path | None = None,
        assets_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
        auto_reload: bool = False,
        globals: dict[str, Any] | None = None,
        verify_on_startup: bool = False,
    ):
        self._transport = transport
        self._from_email = from_email
        self._from_name = from_name
        self._sender = f"{from_name} <{from_email}>" if from_name else from_email
        self._templates_dir = Path(templates_dir) if templates_dir else None

        self._tmpl: MjmlTemplateEnvironment | None = None

        if templates_dir:
            _cache = cache_dir or (Path(templates_dir) / ".cache")
            self._tmpl = MjmlTemplateEnvironment(
                templates_dir=templates_dir,
                assets_dir=assets_dir,
                cache_dir=_cache,
                auto_reload=auto_reload,
                extra_globals=globals or {},
            )

        if verify_on_startup:
            try:
                loop = asyncio.get_event_loop()
                ok = loop.run_until_complete(transport.verify())
                if not ok:
                    logger.warning(
                        "Mailer: transport %s failed startup connectivity check",
                        type(transport).__name__,
                    )
            except Exception:
                logger.exception("Mailer: startup verification raised")

    @staticmethod
    async def _resolve_attachments(
        attachments: list[Attachment],
    ) -> list[ResolvedAttachment]:
        """
        Resolve all attachments
        """
        if not attachments:
            return []

        return list(await asyncio.gather(*[a.resolve() for a in attachments]))

    def _render_template_content(
        self,
        template: str,
        context: dict[str, Any],
    ) -> tuple[str | None, str | None, str]:
        transport_render = self._transport.render_template(
            template=template,
            context=context,
            templates_dir=self._templates_dir,
        )
        if transport_render is not None:
            return transport_render

        else:
            if not self._tmpl:
                raise MailerTemplateError(
                    "Cannot render template emails: no templates_dir was configured. "
                    "Pass templates_dir= to Mailer()."
                )
            return self._tmpl.render(template, **context), None, template

    async def send(
        self,
        *,
        to: str | list[str],
        subject: str,
        html: str | None = None,
        text: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> MailerResult:
        """
        Send a raw email.

        Examples:

            await mailer.send(
                to          = "user@example.com",
                subject     = "Hello",
                html        = "<p>Hi</p>",
                attachments = [Attachment.from_url("https://example.com/file.pdf")],
            )
        """
        recipients = [to] if isinstance(to, str) else to
        resolved = await self._resolve_attachments(attachments or [])
        payload = MailerPayload(
            sender=self._sender,
            recipients=recipients,
            subject=subject,
            html_content=html,
            text_content=text,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments or [],
        )
        resolved_req = ResolvedMailerPayload(payload, resolved)
        return await self._transport.send(resolved_req)

    async def send_template(
        self,
        *,
        to: str | list[str],
        subject: str,
        template: str,
        context: dict[str, Any] | None = None,
        text: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> MailerResult:
        """
        Send template email

        Examples:

            await mailer.send_template(
                to          = "user@example.com",
                subject     = "Your invoice",
                template    = "email_invoice.mjml.html",
                context     = {"name": "Daniel", "total": "$99"},
                attachments = [
                    Attachment.from_url("https://cdn.example.com/invoices/99.pdf"),
                    Attachment.from_path("/tmp/tos.pdf", filename="terms.pdf"),
                ],
            )
        """

        if not self._tmpl:
            transport_render = self._transport.render_template(
                template=template,
                context=context or {},
                templates_dir=self._templates_dir,
            )
            if transport_render is None:
                raise MailerTemplateError(
                    "Cannot send template emails: no templates_dir was configured. " "Pass templates_dir= to Mailer()."
                )

        ctx = context or {}
        render_task = asyncio.to_thread(self._render_template_content, template, ctx)
        attach_task = self._resolve_attachments(attachments or [])
        (html, rendered_text, template_name), resolved = await asyncio.gather(render_task, attach_task)

        recipients = [to] if isinstance(to, str) else to
        payload = MailerPayload(
            sender=self._sender,
            recipients=recipients,
            subject=subject,
            template_name=template_name,
            html_content=html,
            text_content=text if text is not None else rendered_text,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments or [],
        )
        resolved_req = ResolvedMailerPayload(payload, resolved)
        return await self._transport.send(resolved_req)

    async def batch_send_template(
        self,
        *,
        messages: list[MailerTemplateMessage],
    ) -> list[MailerResult]:
        """
        Send multiple template emails.

        Each element of `messages` is a kwargs dict for send_template().
        All messages are rendered and their attachments resolved concurrently
        before being handed to the transport.

        Examples:

            await mailer.batch_send_template(messages=[
                {
                    "to": "a@x.com",
                    "subject": "Invoice #1",
                    "template": "email_invoice.mjml.html",
                    "context": {"name": "Alice"},
                    "attachments": [Attachment.from_url("https://.../inv1.pdf")],
                },
                {
                    "to": ["b@x.com"],
                    "subject": "Invoice #2",
                    "template": "email_invoice.mjml.html",
                    "context": {"name": "Bob"},
                    "attachments": [Attachment.from_url("https://.../inv2.pdf")],
                },
            ])
        """

        async def _prepare(msg: MailerTemplateMessage) -> ResolvedMailerPayload:
            tmpl = msg["template"]
            context = msg.get("context", {})
            raw_atts = msg.get("attachments", [])

            render_task = asyncio.to_thread(self._render_template_content, tmpl, context)
            attach_task = self._resolve_attachments(raw_atts)
            (html, rendered_text, template_name), resolved = await asyncio.gather(
                render_task,
                attach_task,
            )

            recipients = msg["to"] if isinstance(msg["to"], list) else [msg["to"]]
            req = MailerPayload(
                sender=self._sender,
                recipients=recipients,
                subject=msg["subject"],
                template_name=template_name,
                html_content=html,
                text_content=(msg.get("text") if msg.get("text", None) is not None else rendered_text),
                cc=msg.get("cc"),
                bcc=msg.get("bcc"),
                reply_to=msg.get("reply_to"),
                attachments=raw_atts,
            )
            return ResolvedMailerPayload(req, resolved)

        resolved_requests = await asyncio.gather(*[_prepare(m) for m in messages])
        return await self._transport.batch_send(list(resolved_requests))

    def add_global(self, name: str, value: Any) -> None:
        """
        Register an extra global in the template environment at runtime.
        """
        if self._tmpl:
            self._tmpl.add_global(name, value)

    def add_filter(self, name: str, fn: Any) -> None:
        """
        Register an extra Jinja2 filter at runtime.
        """
        if self._tmpl:
            self._tmpl.add_filter(name, fn)

    def render(self, template: str, **context: Any) -> str:
        """
        Render a template to HTML or text without sending anything.
        """

        result = self._render_template_content(template, context)

        if result[0]:
            return result[0]
        elif result[1]:
            return result[1]
        else:
            raise MailerTemplateError(
                f"Template {template} could not be rendered to HTML or text. Check your template and context."
            )
