from typing import Any

from fastapi_pagination import LimitOffsetPage
from fastapi_pagination.cursor import CursorPage

type PageType = CursorPage[Any] | LimitOffsetPage[Any]
