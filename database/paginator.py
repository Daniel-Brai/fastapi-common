from typing import Any, Callable, Sequence, Type

from sqlalchemy import Select, Selectable
from sqlalchemy.orm import Query
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.pagination import (
    CursorPage,
    CursorParams,
    Filter,
    LimitOffsetPage,
    LimitOffsetParams,
    apaginate,
    set_page,
    set_params,
)


class Paginator[ModelType: SQLModel]:
    """
    Builder class for paginating queries.
    """

    def __init__(self, db: AsyncSession, query: Select | Query | Selectable):
        self._db = db
        self._query = query
        self._params: CursorParams | LimitOffsetParams | None = None
        self._page_schema: Type[Any] | None = None
        self._filter: Filter | None = None
        self._count_query: Select | Query | None = None
        self._transformer: Callable[[Sequence[ModelType]], Sequence[Any]] | None = None

    def with_params(self, params: CursorParams | LimitOffsetParams) -> "Paginator[ModelType]":
        """
        Set the pagination parameters (either CursorParams or LimitOffsetParams depending on the pagination type).
        """

        self._params = params
        return self

    def with_schema(self, page_schema: Type[Any]) -> "Paginator[ModelType]":
        """
        Set the model either a database model or pydantic model to use for the page items.

        This is required for both cursor and limit-offset pagination to ensure the output is properly serialized.
        """

        self._page_schema = page_schema
        return self

    def with_filter(self, filters: Filter | None) -> "Paginator[ModelType]":
        """
        Set an optional Filter object to apply additional filtering and sorting to the query before pagination.

        This allows you to reuse the same pagination logic with different filtering criteria.
        """

        self._filter = filters
        return self

    def with_count_query(self, count_query: Select | Query | None) -> "Paginator[ModelType]":
        """
        An optional count query for limit-offset pagination. If not provided, the paginator will attempt to generate one automatically.

        For cursor pagination, this is typically not needed and can be omitted for better performance.
        """

        self._count_query = count_query
        return self

    def with_transformer(
        self, transformer: Callable[[Sequence[ModelType]], Sequence[Any]] | None
    ) -> "Paginator[ModelType]":
        """
        Set a transformer function to convert database models to output schemas.
        """

        self._transformer = transformer
        return self

    async def execute_cursor(self) -> CursorPage[Any]:
        """
        Execute the paginated query using cursor pagination and return a CursorPage.
        """

        if not isinstance(self._params, CursorParams):
            raise ValueError(
                "CursorPagination parameters (params) are required for execute_cursor. use ``with_params(CursorParams(...))``"
            )

        if self._page_schema is None:
            raise ValueError(
                "Page schema (schema) is required either use a pydantic model or database model as the page schema and set it with ``with_schema(...)``"
            )

        filtered_query = self._query
        filtered_count_query = self._count_query

        if self._filter is not None:
            filtered_query = self._filter.sort(self._filter.filter(filtered_query))  # type: ignore

        if filtered_count_query is not None and self._filter is not None:
            filtered_count_query = self._filter.filter(filtered_count_query)  # type: ignore

        set_page(CursorPage[self._page_schema])
        set_params(self._params)

        return await apaginate(
            conn=self._db,  # type: ignore
            query=filtered_query,  # type: ignore
            count_query=filtered_count_query,  # type: ignore
            transformer=self._transformer,
        )

    async def execute_offset(self) -> LimitOffsetPage[Any]:
        """
        Execute the paginated query using limit-offset pagination and return a LimitOffsetPage.
        """

        if not isinstance(self._params, LimitOffsetParams):
            raise ValueError(
                "LimitOffset parameters (params) are required for execute_offset. use ``with_params(LimitOffsetParams(...))``"
            )

        if self._page_schema is None:
            raise ValueError(
                "Page schema (schema) is required either use a pydantic model or database model as the page schema and set it with ``with_schema(...)``"
            )

        filtered_query = self._query
        filtered_count_query = self._count_query

        if self._filter:
            filtered_query = self._filter.sort(self._filter.filter(filtered_query))  # type: ignore

        if filtered_count_query is not None and self._filter is not None:
            filtered_count_query = self._filter.filter(filtered_count_query)  # type: ignore

        set_page(LimitOffsetPage[self._page_schema])
        set_params(self._params)

        return await apaginate(
            conn=self._db,  # type: ignore
            query=filtered_query,  # type: ignore
            count_query=filtered_count_query,  # type: ignore
            transformer=self._transformer,
        )
