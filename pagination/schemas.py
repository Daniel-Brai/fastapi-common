from fastapi_pagination.bases import CursorRawParams
from fastapi_pagination.cursor import CursorParams as _CursorParams
from fastapi_pagination.cursor import decode_cursor
from fastapi_pagination.limit_offset import LimitOffsetParams as _LimitOffsetParams
from pydantic import BaseModel, Field, PositiveInt


class CursorParams(_CursorParams):
    """
    A custom `CursorParams` class that extends FastAPI Pagination's cursor pagination.

    It limits the page size to a default of 10 items per page and a maximum of 100 items per page.
    Includes total count in the response.
    """

    size: PositiveInt = Field(default=10, le=100, description="Number of items per page (max 100)")

    def to_raw_params(self) -> CursorRawParams:
        return CursorRawParams(
            cursor=decode_cursor(
                self.cursor,
                to_str=self.str_cursor,
                quoted=self.quoted_cursor,
            ),
            size=self.size,
            include_total=True,
        )

    def to_cache_key(self) -> str:
        """
        Generate a cache key based on the cursor and size params
        """

        key = f"cursor:{self.cursor}:size:{self.size}".encode().hex()

        return key


class CursorPaginationMetadata(BaseModel):
    """
    Metadata for cursor-based pagination responses.

    Attributes:
        total (int | None): Total number of items available.
        current_page (str | None): Cursor to refetch the current page.
        current_page_backwards (str | None): Cursor to refetch the current page starting from the last item.
        previous_page (str | None): Cursor for the previous page.
        next_page (str | None): Cursor for the next page.
    """

    total: int | None = Field(default=None, description="Total number of items available")
    current_page: str | None = Field(default=None, description="Cursor to refetch the current page")
    current_page_backwards: str | None = Field(
        default=None,
        description="Cursor to refetch the current page starting from the last item",
    )
    previous_page: str | None = Field(default=None, description="Cursor for the previous page")
    next_page: str | None = Field(default=None, description="Cursor for the next page")


class LimitOffsetParams(_LimitOffsetParams):
    """
    A custom `LimitOffsetParams` that changes the default page size to 10 and
    enforces the same maximum of 100 items per page as the cursor params.
    """

    limit: PositiveInt = Field(default=10, le=100, description="Number of items per page (max 100)")


class LimitOffsetPaginationMetadata(BaseModel):
    """
    Metadata for limit/offset-based pagination responses.

    Attributes:
        total (int | None): Total number of items available.
        limit (int): Number of items requested per page.
        offset (int): Current offset in the result set.
        previous_offset (int | None): Offset for the previous page, if any.
        next_offset (int | None): Offset for the next page, if any.
    """

    total: int | None = Field(default=None, description="Total number of items available")
    limit: int = Field(description="Number of items requested per page")
    offset: int = Field(description="Current offset in the result set")
    previous_offset: int | None = Field(default=None, description="Offset for the previous page, if any")
    next_offset: int | None = Field(default=None, description="Offset for the next page, if any")
