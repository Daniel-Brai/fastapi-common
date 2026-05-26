from typing import Any, Awaitable, Callable

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from lib.notifications.schemas import PushSubscriptionType

type DBEngine = Engine | AsyncEngine

type PushSubscriptionLoader = Callable[[Any], Awaitable[list[PushSubscriptionType]]]

type PushSubscriptionPruner = Callable[[Any, list[str]], Awaitable[None]]
