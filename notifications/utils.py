import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from py_vapid.utils import b64urlencode

from lib.notifications.config import get_registry
from lib.notifications.constants import SSE_CHANNEL_PREFIX
from lib.notifications.emitter import EventEmitter
from lib.notifications.exceptions import NotificationNotConfigured


def channel_key(prefix: str, recipient_id: Any) -> str:
    """
    Generate a channel key for a given recipient.

    The prefix is typically the notification class name or transport name, and
    the recipient_id is a unique identifier for the recipient (e.g. user ID).
    """

    return f"{prefix}:{str(recipient_id)}"


def load_url_safe_vapid_public_key(path: str | Path, format: Literal["base64", "pem"] = "pem") -> str:
    """
    Load a VAPID public key from the specified file path and return a URL-safe base64-encoded string suitable
    for use in web push notifications.

    Args:
        path (str | Path): The file path to the VAPID public key.
        format (Literal["base64", "pem"]): The format of the key to load.

    Returns:
        str: A URL-safe base64-encoded string representation of the VAPID public key.
    """

    key_data = Path(path).read_text(encoding="utf-8").strip()

    if format == "base64":
        return key_data

    public_key = serialization.load_pem_public_key(key_data.encode("utf-8"), backend=default_backend())
    raw_key = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    return b64urlencode(raw_key)


async def subscribe_sse(
    recipient_id: Any,
    event_emitter: EventEmitter,
) -> AsyncIterator[dict[str, Any]]:
    """
    Async generator that yields SSE event dictionaries for a recipient.

    Mount this inside a FastAPI SSE endpoint::

        from sse_starlette.sse import EventSourceResponse
        from lib.notifications.utils import subscribe_sse
        from lib.notifications.config import get_registry

        @router.get("/notifications/stream")
        async def stream(user = Depends(require_auth)):
            emitter = get_registry().event_emitter
            return EventSourceResponse(subscribe_sse(user.id, emitter))

    EventSourceResponse will serialize these event dictionaries into valid
    SSE messages and handle keepalive pings automatically.
    """

    channel = channel_key(SSE_CHANNEL_PREFIX, recipient_id)

    async for message in event_emitter.subscribe(channel):
        yield {"data": message}


def send_fcm_push(
    token: str,
    message: dict[str, Any],
    record_id: int | None = None,
) -> None:
    """
    Execute a single FCM v1 push notification synchronously.
    """

    credentials_source = get_registry().fcm_credentials
    if credentials_source is None:
        raise NotificationNotConfigured("Notification not configured for FCMTransport: fcm_credentials not set.")

    try:
        import google.auth.transport.requests
        import google.oauth2.service_account as sa
        import httpx
    except ImportError as exc:
        raise ImportError("FCMTransport requires google-auth and httpx: " "pip install google-auth httpx") from exc

    if isinstance(credentials_source, str):
        creds = sa.Credentials.from_service_account_file(
            credentials_source,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
    else:
        creds = credentials_source

    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)

    project_id = creds.project_id
    fcm_endpoint = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    notification_body: dict[str, Any] = {
        "title": message.get("title", ""),
        "body": message.get("body", ""),
    }
    if message.get("image_url"):
        notification_body["image"] = message["image_url"]

    fcm_data: dict[str, str] = {}
    if record_id is not None:
        fcm_data["notification_id"] = str(record_id)
    if message.get("url"):
        fcm_data["url"] = message["url"]
    if message.get("data"):
        for k, v in message["data"].items():
            fcm_data[str(k)] = str(v)

    payload = {
        "message": {
            "token": token,
            "notification": notification_body,
            "data": fcm_data,
        }
    }

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }

    resp = httpx.post(fcm_endpoint, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
