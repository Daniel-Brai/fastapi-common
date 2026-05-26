from fastapi_filter import FilterDepends, with_prefix
from fastapi_pagination import add_pagination, set_page, set_params
from fastapi_pagination.cursor import CursorPage
from fastapi_pagination.ext.sqlalchemy import apaginate, paginate
from fastapi_pagination.limit_offset import LimitOffsetPage

from .filter import Filter
from .schemas import CursorPaginationMetadata, CursorParams, LimitOffsetPaginationMetadata, LimitOffsetParams
from .types import PageType

__all__ = [
    "Filter",
    "CursorPaginationMetadata",
    "CursorParams",
    "LimitOffsetPaginationMetadata",
    "LimitOffsetParams",
    "CursorPage",
    "LimitOffsetPage",
    "add_pagination",
    "paginate",
    "apaginate",
    "set_page",
    "set_params",
    "PageType",
    "with_prefix",
    "FilterDepends",
]
