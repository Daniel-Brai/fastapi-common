from typing import Any, Type

from pydantic import BaseModel
from sqlalchemy import Select, Selectable, bindparam
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Query
from sqlmodel import SQLModel, col, delete
from sqlmodel import inspect as sa_inspect
from sqlmodel import update
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.database.paginator import Paginator
from lib.database.query import QueryBuilder

type DataInput = BaseModel | dict[str, Any]


class Repository[
    ModelType: SQLModel,
    IDType: int | str | Any,
]:
    """
    Repository provides common CRUD operations, a query builder and pagination for a given SQLModel model.

    All methods are async and do NOT commit automatically

    As such transaction control belongs to the service layer.

    **Note**: The repository expects the model to have a primary key named ``id`` for `update` and `delete` operations.

    Example usage:

        class UserRepository(Repository[User, UUID]):
            def __init__(self, db: AsyncSession):
                super().__init__(User, db)
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession) -> None:
        self._model = model
        self.db = db

    @property
    def model(self) -> Type[ModelType]:
        """
        The SQLModel model class associated with this repository.
        """
        return self._model

    async def refresh_instance(self, instance: ModelType) -> ModelType:
        """
        Refresh an instance from the database.

        Args:
            instance (ModelType): The instance to refresh.

        Returns:
            ModelType: The refreshed instance.
        """
        await self.db.refresh(instance)
        return instance

    async def flush(self) -> None:
        """
        Flush pending changes to the database without committing.
        """
        return await self.db.flush()

    async def commit(self) -> None:
        """
        Commit the current transaction.
        """
        return await self.db.commit()

    def query(self) -> QueryBuilder[ModelType]:
        """
        Start a new query builder

        Example:

            users = await repo.query().where(User.is_active == True).all()
        """
        return QueryBuilder(self._model, self.db)

    def paginate(
        self,
        *,
        query: Select | Query | Selectable,
    ) -> Paginator[ModelType]:
        """
        Return a Paginator builder for the given query.

        Example:

            page = await repo.paginate(
                repo.query().where(User.is_active == True)
            ).with_schema(UserPage).with_filter(user_filter).execute_cursor()

        """
        return Paginator(self.db, query)

    async def get(self, id: IDType) -> ModelType | None:
        """
        Get by primary key.
        """
        return await self.db.get(self._model, id)

    async def get_by(self, **kwargs: Any) -> ModelType | None:
        """
        Get by equality filters (e.g., get_by(email="user@example.com")).
        """
        return await self.query().filter_by(**kwargs).first()

    async def create(self, data: DataInput) -> ModelType:
        """
        Create a new record. Does NOT commit
        """
        if isinstance(data, BaseModel):
            data = data.model_dump()

        instance = self._model(**data)
        self.db.add(instance)
        await self.db.flush()
        return instance

    async def update(self, id: IDType, data: DataInput) -> ModelType | None:
        """
        Update by primary key. Returns updated instance or None.
        """

        existing_entity = await self.get(id)

        if not existing_entity:
            return None

        if isinstance(data, BaseModel):
            data = data.model_dump(exclude_unset=True)

        existing_entity.sqlmodel_update(data)
        self.db.add(existing_entity)

        await self.flush()

        return existing_entity

    async def update_with_obj(self, instance: ModelType, data: DataInput) -> ModelType:
        """
        Update an existing instance with new data. Returns the updated instance.
        """
        if isinstance(data, BaseModel):
            data = data.model_dump(exclude_unset=True)

        instance.sqlmodel_update(data)
        self.db.add(instance)

        return instance

    async def delete(self, id: IDType) -> bool:
        """
        Delete by primary key. Returns True if deleted.
        """

        stmt = delete(self._model).where(self._model.id == id).returning(self._model.id)  # type: ignore[attr-defined]
        result = await self.db.exec(stmt)
        await self.flush()
        return result.one_or_none() is not None

    async def delete_by(self, **filters: Any) -> int:
        """
        Delete by filters. Returns number of rows deleted.
        """
        stmt = delete(self._model).filter_by(**filters)
        result = await self.db.exec(stmt)
        await self.flush()
        return result.rowcount

    async def delete_with_obj(self, instance: ModelType) -> bool:
        """
        Delete an instance. Returns True if deleted.
        """
        await self.db.delete(instance)
        await self.flush()
        return True

    async def exists(self, **filters: Any) -> bool:
        """
        Check if any record exists with given filters.
        """
        return await self.query().filter_by(**filters).limit(1).count() > 0

    async def refresh(self, instance: ModelType) -> ModelType:
        """
        Refresh an instance from the database.
        """
        await self.db.refresh(instance)
        return instance

    async def upsert(
        self,
        data: DataInput,
        conflict_columns: list[str] | None = None,
        update_columns: list[str] | None = None,
    ) -> ModelType:
        """
        Upsert using PostgreSQL's ON CONFLICT DO UPDATE.
        - data: dict or Pydantic model (exclude_unset respected).
        - conflict_columns: columns that define the unique conflict (default = primary key).
        - update_columns: columns to update on conflict (default = all non-pk columns).
        """

        if isinstance(data, BaseModel):
            data = data.model_dump(exclude_unset=True)

        model_inspect = sa_inspect(self._model)

        pk_columns = [col.name for col in model_inspect.primary_key]  # type: ignore
        conflict_cols = conflict_columns or pk_columns

        all_columns = [col.name for col in model_inspect.mapper.columns]  # type: ignore
        if update_columns is None:
            update_cols = [col for col in all_columns if col not in pk_columns]
        else:
            update_cols = update_columns

        stmt = insert(self._model).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={col: stmt.excluded[col] for col in update_cols},
        ).returning(self._model)

        result = await self.db.exec(stmt)
        await self.flush()
        return result.scalar_one()

    async def bulk_create(self, objs: list[DataInput]) -> list[ModelType]:
        """
        Create multiple records in one batch.
        """

        dicts = [
            obj.model_dump() if isinstance(obj, BaseModel) else obj for obj in objs
        ]

        instances = [self._model(**d) for d in dicts]
        self.db.add_all(instances)
        await self.flush()
        return instances

    async def bulk_update(
        self, ids: list[IDType], data_list: list[dict[str, Any]]
    ) -> int:
        """
        Update multiple records with different data in one round trip.

        Args:
            ids: List of primary keys (must match length of data_list).
            data_list: List of dicts, each containing the fields to update for the corresponding id.

        Returns:
            Number of rows updated.

        Example:

            ids = [1, 2]
            data_list = [{"title": "New Title 1"}, {"title": "New Title 2"}]
            await repo.bulk_update(ids, data_list)
        """

        if not ids or len(ids) != len(data_list):
            raise ValueError(
                "ids and data_list must have same length and cannot be empty"
            )

        pk_column = self._model.id  # type: ignore[attr-defined]

        update_keys = set()
        for data in data_list:
            update_keys.update(data.keys())
        update_keys = list(update_keys)

        total_rows = 0

        for id_, data in zip(ids, data_list):
            stmt = (
                update(self._model)
                .where(pk_column == id_)
                .values(**data)
                .execution_options(synchronize_session=None)
            )
            result = await self.db.exec(stmt)
            total_rows += result.rowcount or 0

        await self.db.flush()
        return total_rows

    async def bulk_upsert(
        self,
        objs: list[DataInput],
        conflict_columns: list[str] | None = None,
        update_columns: list[str] | None = None,
    ) -> list[ModelType]:
        """
        Upsert multiple records using PostgreSQL's ON CONFLICT DO UPDATE.

        Returns list of instances (either inserted or updated).
        """

        if not objs:
            return []

        dicts = [
            obj.model_dump(exclude_unset=True) if isinstance(obj, BaseModel) else obj
            for obj in objs
        ]

        model_inspect = sa_inspect(self._model)

        pk_columns = [col.name for col in model_inspect.primary_key]  # type: ignore
        conflict_cols = conflict_columns or pk_columns

        all_columns = [col.name for col in model_inspect.mapper.columns]  # type: ignore
        if update_columns is None:
            update_cols = [col for col in all_columns if col not in pk_columns]
        else:
            update_cols = update_columns

        stmt = insert(self._model).values(dicts)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_={col: stmt.excluded[col] for col in update_cols},
        ).returning(self._model)

        result = await self.db.exec(stmt)
        await self.flush()
        return list(result.scalars().all())

    async def bulk_delete(self, ids: list[IDType]) -> int:
        """
        Delete multiple records by primary key. Returns number of rows deleted.
        """
        if not ids:
            return 0

        stmt = delete(self._model).where(col(self._model.id).in_(ids))  # type: ignore[attr-defined]
        result = await self.db.exec(stmt)
        await self.flush()
        return result.rowcount
