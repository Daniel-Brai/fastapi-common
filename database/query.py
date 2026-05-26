from typing import Any, Callable, Sequence, Type

from pydantic import NonNegativeInt
from sqlalchemy.orm import contains_eager, joinedload, selectinload
from sqlalchemy.sql import ColumnElement
from sqlmodel import SQLModel
from sqlmodel import exists as sa_exists
from sqlmodel import func, not_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.database.paginator import Paginator


class QueryBuilder[ModelType: SQLModel]:
    """
    Fluent, chainable query builder for SQLAlchemy 2.0 async sessions.

    It provides a more convenient API for building complex queries with method chaining.

    Example usage:

        # Get all active users ordered by name
        users = await QueryBuilder(User, session).where(User.active == True).order_by(User.name).all()
        #
        # Get the first post with a specific title
        post = await QueryBuilder(Post, session).filter_by(title="Hello World").first()

        # Get users with at least one published post
        users = await QueryBuilder(User, session).where_exists(
            lambda q: q.join(Post).where(Post.published == True)
        ).all()
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession) -> None:
        self.model = model
        self.db = db
        self._stmt = select(model)
        self._options: list[Any] = []

    @property
    def stmt(self):
        """
        Get the current SQLAlchemy statement object.
        """
        return self._stmt

    def with_only_columns(self, *columns: Any) -> "QueryBuilder[ModelType]":
        """
        Replace the SELECT columns with the specified columns.
        """
        self._stmt = self._stmt.with_only_columns(*columns)
        return self

    def where(self, *conditions: ColumnElement[bool]) -> "QueryBuilder[ModelType]":
        """
        Add WHERE conditions (AND).
        """
        self._stmt = self._stmt.where(*conditions)
        return self

    def filter_by(self, **kwargs: Any) -> "QueryBuilder[ModelType]":
        """
        Add equality conditions using keyword arguments.
        """
        return self.where(*[getattr(self.model, k) == v for k, v in kwargs.items()])

    def or_where(self, *conditions: ColumnElement[bool]) -> "QueryBuilder[ModelType]":
        """
        Add OR conditions.
        """
        if conditions:
            self._stmt = self._stmt.where(or_(*conditions))
        return self

    def not_where(self, condition: ColumnElement[bool]) -> "QueryBuilder[ModelType]":
        """
        Add a NOT condition.
        """
        return self.where(not_(condition))

    def join(self, target: Any, *onclause: Any, isouter: bool = False) -> "QueryBuilder[ModelType]":
        """
        Join another table or relationship.
        - target: model class or relationship attribute (string or attribute).
        - onclause: optional join condition (uses FK if omitted).
        - isouter: if True, LEFT OUTER JOIN.
        """

        self._stmt = self._stmt.join(target, *onclause, isouter=isouter)
        return self

    def outerjoin(self, target: Any, *onclause: Any) -> "QueryBuilder[ModelType]":
        """
        Shortcut for LEFT OUTER JOIN.
        """
        return self.join(target, *onclause, isouter=True)

    def options(self, *options: Any) -> "QueryBuilder[ModelType]":
        """
        Add loader options (joinedload, selectinload, etc.)
        """
        self._options.extend(options)
        self._stmt = self._stmt.options(*options)
        return self

    def joinload(self, attr: Any) -> "QueryBuilder[ModelType]":
        """
        Eager load a relationship using JOIN.
        """
        return self.options(joinedload(attr))

    def selectinload(self, attr: Any) -> "QueryBuilder[ModelType]":
        """
        Eager load a relationship using a separate SELECT (better for to-many).
        """
        return self.options(selectinload(attr))

    def contains_eager(self, attr: Any) -> "QueryBuilder[ModelType]":
        """
        Indicate that a relationship is already loaded by a join.
        """
        return self.options(contains_eager(attr))

    def where_exists(
        self,
        subquery_builder: Callable[["QueryBuilder[ModelType]"], "QueryBuilder[Any]"],
    ) -> "QueryBuilder[ModelType]":
        """
        Add EXISTS condition using a subquery builder.
        """
        sub_builder = subquery_builder(QueryBuilder(self.model, self.db))
        return self.where(sa_exists(sub_builder._stmt))

    def where_not_exists(
        self,
        subquery_builder: Callable[["QueryBuilder[ModelType]"], "QueryBuilder[Any]"],
    ) -> "QueryBuilder[ModelType]":
        """
        Add NOT EXISTS condition using a subquery builder.
        """
        sub_builder = subquery_builder(QueryBuilder(self.model, self.db))
        return self.where(~sa_exists(sub_builder._stmt))

    def order_by(self, *columns: Any) -> "QueryBuilder[ModelType]":
        """
        Set ordering (can be column objects or strings).
        """
        self._stmt = self._stmt.order_by(*columns)
        return self

    def limit(self, limit: NonNegativeInt) -> "QueryBuilder[ModelType]":
        """
        Limit the number of rows.
        """
        self._stmt = self._stmt.limit(limit)
        return self

    def offset(self, offset: NonNegativeInt) -> "QueryBuilder[ModelType]":
        """
        Set offset.
        """
        self._stmt = self._stmt.offset(offset)
        return self

    def distinct(self, *columns: Any) -> "QueryBuilder[ModelType]":
        """
        Add DISTINCT (optionally on columns).
        """
        self._stmt = self._stmt.distinct(*columns)
        return self

    def group_by(self, *columns: Any) -> "QueryBuilder[ModelType]":
        """
        Add GROUP BY.
        """
        self._stmt = self._stmt.group_by(*columns)
        return self

    def having(self, *conditions: ColumnElement[bool]) -> "QueryBuilder[ModelType]":
        """
        Add HAVING condition (requires GROUP BY).
        """
        self._stmt = self._stmt.having(*conditions)
        return self

    async def all(self) -> Sequence[ModelType]:
        """
        Execute and return all results.
        """
        result = await self.db.exec(self._stmt)  # type: ignore
        return result.unique().all()

    async def first(self) -> ModelType | None:
        """
        Return the first result or None.
        """
        stmt = self._stmt.limit(1)
        result = await self.db.exec(stmt)  # type: ignore
        return result.unique().first()

    async def one_or_none(self) -> ModelType | None:
        """
        Return exactly one result or None.
        """
        result = await self.db.exec(self._stmt)  # type: ignore
        return result.unique().one_or_none()

    async def scalar(self) -> Any:
        """
        Return a single scalar value (e.g., for count queries).
        """
        result = await self.db.exec(self._stmt)  # type: ignore
        return result.one()

    async def exec(self) -> Any:
        """
        Execute the statement and return the raw result.
        """
        return await self.db.exec(self._stmt)  # type: ignore

    async def count(self) -> int:
        """
        Return the count of rows matching the query (ignores limit/offset).
        """
        count_stmt = select(func.count()).select_from(self._stmt.subquery())
        result = await self.db.exec(count_stmt)
        return result.one()

    def paginate(self) -> "Paginator[ModelType]":
        """
        Return a Paginator builder from the current query context.

        Example:

            page = await repo.query() \\
                .where(User.is_active == True) \\
                .selectinload(User.profile) \\
                .order_by(User.created_at.desc()) \\
                .paginate() \\
                .with_params(params) \\
                .with_schema(UserSchema) \\
                .with_filter(user_filter) \\
                .with_count_query(select(func.count()).select_from(User)) \\
                .with_transformer(lambda users: [UserSchema.model_validate(u) for u in users]) \\
                .execute_cursor()
        """

        return Paginator(self.db, self._stmt)
