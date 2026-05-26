from __future__ import annotations

import base64
import re
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid

from lib.logger import get_logger
from lib.mailer.exceptions import MailerAuthError, MailerError, MailerInvalidRecipientError
from lib.mailer.schemas import MailerResult, ResolvedMailerPayload
from lib.mailer.transports.base import AbstractTransport

logger = get_logger("lib.mailer.transports.ses")


class SESTransport(AbstractTransport):
    """
    AWS SES Transport.

    Examples:

        SESTransport(region="eu-west-1")                 # IAM role / env creds
        SESTransport(
            region     = "us-east-1",
            access_key = "AKIA...",
            secret_key = "...",
        )
    """

    def name(self) -> str:
        return "ses"

    def __init__(
        self,
        region: str,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        try:
            import boto3

            self._boto3 = boto3
        except ImportError as exc:
            raise ImportError("boto3 is required for SESTransport: pip install boto3") from exc

        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._client = self._make_client()

    def _make_client(self):
        kwargs: dict = {"region_name": self._region}
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key

        return self._boto3.client("ses", **kwargs)

    async def verify(self) -> bool:
        try:
            self._client.get_send_quota()
            return True
        except Exception as exc:
            logger.error("SESTransport: SES connectivity check failed: %s", exc)
            return False

    async def send(self, payload: ResolvedMailerPayload) -> MailerResult:
        from botocore.exceptions import ClientError

        try:
            domain = payload.sender.split("@")[-1].rstrip(">")
            message_id = payload.message_id or make_msgid(domain=domain)

            html = payload.html_content or ""
            html, inline_images = self._extract_inline_images(html) if html else (html, [])

            if payload.attachments or inline_images:
                raw = self._build_raw_message(payload, message_id, html, inline_images)
                destinations = list(payload.recipients) + (payload.cc or []) + (payload.bcc or [])
                resp = self._client.send_raw_email(
                    RawMessage={"Data": raw},
                    Source=payload.sender,
                    Destinations=destinations,
                )
            else:
                resp = self._send_simple(payload, html, message_id)

            return MailerResult(
                transport=self.name(),
                message_id=resp.get("MessageId", message_id),
                status="sent",
                raw_response=resp,
            )

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            message = exc.response["Error"]["Message"]
            logger.error("SESTransport: SES error %s: %s", code, message)
            if code == "InvalidParameterValue":
                raise MailerInvalidRecipientError() from exc
            if code in ("InvalidClientTokenId", "SignatureDoesNotMatch"):
                raise MailerAuthError("SES authentication failed") from exc
            raise MailerError(f"SES error: {message}") from exc
        except Exception as exc:
            logger.exception("SESTransport: SES send failed")
            raise MailerError(f"SES send failed: {exc}") from exc

    def _send_simple(self, payload, html: str, message_id: str) -> dict:
        body: dict = {}
        if payload.text_content:
            body["Text"] = {"Data": payload.text_content, "Charset": "UTF-8"}
        if html:
            body["Html"] = {"Data": html, "Charset": "UTF-8"}

        destination: dict = {"ToAddresses": payload.recipients}
        if payload.cc:
            destination["CcAddresses"] = payload.cc
        if payload.bcc:
            destination["BccAddresses"] = payload.bcc

        return self._client.send_email(
            Source=payload.sender,
            Destination=destination,
            Message={
                "Subject": {"Data": payload.subject, "Charset": "UTF-8"},
                "Body": body,
            },
            ReplyToAddresses=[payload.reply_to] if payload.reply_to else [],
            ReturnPath=payload.sender,
        )

    @staticmethod
    def _extract_inline_images(html: str) -> tuple[str, list[dict]]:
        """
        Replace base64 data URIs with CID references for SES inline images.
        """

        inline: list[dict] = []

        def _replace(match: re.Match) -> str:
            cid = f"image_{len(inline)}"
            inline.append(
                {
                    "cid": cid,
                    "mime_type": match.group(1),
                    "data": match.group(2),
                }
            )
            return f'src="cid:{cid}"'

        modified = re.sub(r'src="data:([^;]+);base64,([^"]+)"', _replace, html)
        return modified, inline

    def _build_raw_message(
        self,
        payload,
        message_id: str,
        html: str,
        inline_images: list[dict],
    ) -> bytes:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = payload.subject
        msg["From"] = payload.sender
        msg["To"] = ", ".join(payload.recipients)

        if payload.cc:
            msg["Cc"] = ", ".join(payload.cc)

        if payload.reply_to:
            msg["Reply-To"] = payload.reply_to

        msg["Message-ID"] = message_id

        msg_related = MIMEMultipart("related")
        msg_alternative = MIMEMultipart("alternative")

        if payload.text_content:
            msg_alternative.attach(MIMEText(payload.text_content, "plain", "utf-8"))

        if html:
            msg_alternative.attach(MIMEText(html, "html", "utf-8"))

        msg_related.attach(msg_alternative)

        for img in inline_images:
            try:
                img_bytes = base64.b64decode(img["data"])
                subtype = img["mime_type"].split("/")[-1] if "/" in img["mime_type"] else "png"
                part = MIMEImage(img_bytes, _subtype=subtype)
                part.add_header("Content-ID", f"<{img['cid']}>")
                part.add_header("Content-Disposition", "inline")
                msg_related.attach(part)
            except Exception as exc:
                logger.error(
                    "SESTransport: Failed to attach inline image %s: %s",
                    img["cid"],
                    exc,
                )

        msg.attach(msg_related)

        for att in payload.attachments:
            part = MIMEApplication(att.content)
            part.add_header("Content-Disposition", f'attachment; filename="{att.filename}"')
            part.add_header("Content-Type", att.content_type)
            msg.attach(part)

        return msg.as_bytes()
