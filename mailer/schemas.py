import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


@dataclass
class ResolvedAttachment:
    """
    A fully-resolved attachment with guaranteed bytes content.
    """

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


class Attachment(BaseModel):
    """
    File attachment for an outgoing email.
    """

    content: bytes | None = None
    url: str | None = None
    path: str | None = None

    filename: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def _validate_source(self) -> "Attachment":
        sources = sum(
            [
                self.content is not None,
                bool(self.url),
                bool(self.path),
            ]
        )
        if sources == 0:
            raise ValueError("Attachment requires exactly one of: content, url, or path")
        if sources > 1:
            raise ValueError("Attachment accepts only one source — " "supply content, url, OR path, not multiple")
        return self

    @classmethod
    def from_bytes(
        cls,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> "Attachment":
        return cls(filename=filename, content=content, content_type=content_type)

    @classmethod
    def from_url(
        cls,
        url: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> "Attachment":
        return cls(url=url, filename=filename, content_type=content_type)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> "Attachment":
        return cls(path=str(path), filename=filename, content_type=content_type)

    async def resolve(self) -> ResolvedAttachment:
        """
        Fetch / read the attachment and return a ResolvedAttachment with bytes.

          content source — returned immediately (no I/O)
          path source    — read from disk synchronously
          url source     — fetched with httpx (async, follows redirects)
                           filename and content_type inferred from response
                           headers when not explicitly supplied

        Raises:
          AttachmentFetchError  — non-2xx response or network error on URL fetch
          AttachmentReadError   — local path cannot be read
        """
        from lib.mailer.exceptions import MailerAttachmentFetchError, MailerAttachmentReadError

        if self.content is not None:
            return ResolvedAttachment(
                filename=self.filename or f"attachment-{uuid4()}",
                content=self.content,
                content_type=self._guess_type(self.filename, self.content_type),
            )

        if self.path is not None:
            p = Path(self.path)
            try:
                data = p.read_bytes()
            except OSError as exc:
                raise MailerAttachmentReadError(f"Cannot read attachment {self.path!r}: {exc}") from exc

            filename = self.filename or p.name
            return ResolvedAttachment(
                filename=filename,
                content=data,
                content_type=self._guess_type(filename, self.content_type),
            )

        return await self._fetch_url(MailerAttachmentFetchError)

    async def _fetch_url(self, exc_cls) -> ResolvedAttachment:
        import httpx

        if not self.url:
            raise exc_cls("URL is required to fetch attachment")

        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            try:
                resp = await client.get(self.url)
            except httpx.RequestError as exc:
                raise exc_cls(f"Failed to fetch attachment from {self.url!r}: {exc}") from exc

        if resp.status_code >= 400:
            raise exc_cls(f"Attachment URL returned HTTP {resp.status_code}: {self.url!r}")

        filename = self.filename or self._filename_from_response(resp, self.url)
        content_type = self.content_type or self._content_type_from_response(resp) or self._guess_type(filename, None)

        return ResolvedAttachment(
            filename=filename,
            content=resp.content,
            content_type=content_type,
        )

    @staticmethod
    def _guess_type(filename: str | None, explicit: str | None) -> str:
        if explicit:
            return explicit

        if filename:
            guessed, _ = mimetypes.guess_type(filename)
            if guessed:
                return guessed

        return "application/octet-stream"

    @staticmethod
    def _filename_from_response(resp, url: str) -> str:
        """
        Infer a filename from Content-Disposition (RFC 6266 / RFC 5987), falling back to the last segment of the URL path.
        """

        cd = resp.headers.get("content-disposition", "")
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename*="):
                try:
                    from urllib.parse import unquote

                    encoded = part[10:].split("'")[-1]
                    name = unquote(encoded)
                    if name:
                        return name
                except Exception:
                    pass

            if part.lower().startswith("filename="):
                name = part[9:].strip().strip('"').strip("'")
                if name:
                    return name

        from urllib.parse import urlparse

        path_segment = os.path.basename(urlparse(url).path)
        return path_segment or f"attachment-{uuid4()}"

    @staticmethod
    def _content_type_from_response(resp) -> str | None:
        ct = resp.headers.get("content-type", "")
        if ct:
            return ct.split(";")[0].strip()

        return None


class MailerPayload(BaseModel):
    """
    Full specification for one outgoing email.
    """

    sender: str
    recipients: list[str]
    subject: str

    cc: list[str] | None = None
    bcc: list[str] | None = None
    reply_to: str | None = None
    message_id: str | None = Field(default_factory=lambda: str(uuid4()))

    template_name: str | None = None
    template_context: dict[str, Any] = Field(default_factory=dict)
    html_content: str | None = None
    text_content: str | None = None

    attachments: list[Attachment] = Field(default_factory=list)


class MailerTemplateMessage(TypedDict):
    """
    Schema for a template message to be sent to a transport
    """

    to: str | list[str]
    subject: str
    template: str
    context: NotRequired[dict[str, Any]]
    text: NotRequired[str | None]
    cc: NotRequired[list[str] | None]
    bcc: NotRequired[list[str] | None]
    reply_to: NotRequired[str | None]
    attachments: NotRequired[list[Attachment]]


@dataclass
class MailerResult:
    transport: str
    message_id: str | None = None
    status: str = "sent"
    error_message: str | None = None
    raw_response: dict[str, Any] | None = None


class ResolvedMailerPayload:
    """
    A MailerPayload with all attachments resolved to bytes, ready to be sent by a transport.
    """

    __slots__ = (
        "sender",
        "recipients",
        "subject",
        "cc",
        "bcc",
        "reply_to",
        "message_id",
        "template_name",
        "html_content",
        "text_content",
        "attachments",
    )

    def __init__(self, req: MailerPayload, attachments: list[ResolvedAttachment]):
        self.sender = req.sender
        self.recipients = req.recipients
        self.subject = req.subject
        self.cc = req.cc
        self.bcc = req.bcc
        self.reply_to = req.reply_to
        self.message_id = req.message_id
        self.template_name = req.template_name
        self.html_content = req.html_content
        self.text_content = req.text_content
        self.attachments = attachments
