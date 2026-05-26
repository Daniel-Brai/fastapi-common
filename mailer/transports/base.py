from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from lib.mailer.schemas import MailerResult, ResolvedMailerPayload


class AbstractTransport(ABC):
    """
    Abstract base class for mailer transports.
    """

    @abstractmethod
    def name(self) -> str:
        """
        Unique name of the transport, e.g "smtp", "sendgrid", etc.
        """
        ...

    @abstractmethod
    async def send(self, payload: "ResolvedMailerPayload") -> "MailerResult": ...

    async def batch_send(self, payloads: list["ResolvedMailerPayload"]) -> list["MailerResult"]:
        results = []
        for payload in payloads:
            results.append(await self.send(payload))

        return results

    async def verify(self) -> bool:
        return True

    def render_template(
        self,
        *,
        template: str,
        context: dict[str, Any] | None = None,
        templates_dir: str | Path | None = None,
    ) -> tuple[str | None, str | None, str] | None:
        return None
