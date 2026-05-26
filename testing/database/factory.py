import inspect

import factory
from factory.alchemy import SESSION_PERSISTENCE_COMMIT, SESSION_PERSISTENCE_FLUSH
from factory.builder import BuildStep, StepBuilder, parse_declarations


class AsyncStepBuilder(StepBuilder):
    """
    Orchestrates the generation process. Awaits the instantiation and post-generation hooks.
    """

    async def build(self, parent_step=None, force_sequence=None):
        pre, post = parse_declarations(
            self.extras,
            base_pre=self.factory_meta.pre_declarations,
            base_post=self.factory_meta.post_declarations,
        )

        if force_sequence is not None:
            sequence = force_sequence
        else:
            sequence = self.factory_meta.next_sequence()

        step = BuildStep(
            builder=self,
            sequence=sequence,
            parent_step=parent_step,
        )
        step.resolve(pre)

        args, kwargs = self.factory_meta.prepare_arguments(step.attributes)

        instance = await self.factory_meta.instantiate(
            step=step,
            args=args,
            kwargs=kwargs,
        )

        postgen_results = {}
        for declaration_name in post.sorted():
            declaration = post[declaration_name]
            declaration_result = declaration.declaration.evaluate_post(
                instance=instance,
                step=step,
                overrides=declaration.context,
            )
            if inspect.isawaitable(declaration_result):
                declaration_result = await declaration_result
            postgen_results[declaration_name] = declaration_result

        self.factory_meta.use_postgeneration_results(
            instance=instance,
            step=step,
            results=postgen_results,
        )
        return instance


class AsyncSQLAlchemyFactory(factory.alchemy.SQLAlchemyModelFactory):
    """
    Factory for SQLAlchemy/SQLModel models with asynchronous support.
    """

    @classmethod
    async def _generate(cls, strategy, params):
        if cls._meta.abstract:
            raise factory.errors.FactoryError(
                f"Cannot generate instances of abstract factory {cls.__name__}; "
                f"Ensure {cls.__name__}.Meta.model is set and {cls.__name__}.Meta.abstract "
                "is either not set or False."
            )

        step = AsyncStepBuilder(cls._meta, params, strategy)
        return await step.build()

    @classmethod
    async def build(cls, **kwargs):
        return await cls._generate(factory.enums.BUILD_STRATEGY, kwargs)

    @classmethod
    async def create(cls, **kwargs):
        return await cls._generate(factory.enums.CREATE_STRATEGY, kwargs)

    @classmethod
    async def build_batch(cls, size, **kwargs):  # type: ignore[override]
        return [await cls.build(**kwargs) for _ in range(size)]

    @classmethod
    async def create_batch(cls, size, **kwargs):  # type: ignore[override]
        return [await cls.create(**kwargs) for _ in range(size)]

    @classmethod
    async def _create(cls, model_class, *args, **kwargs):
        session_factory = getattr(cls._meta, "sqlalchemy_session_factory", None)
        if session_factory:
            cls._meta.sqlalchemy_session = session_factory()  # type: ignore

        session = getattr(cls._meta, "sqlalchemy_session", None)
        if session is None:
            raise factory.errors.FactoryError(
                f"Cannot create {model_class.__name__} instance: sqlalchemy_session not set."
            )

        resolved_args = [await arg if inspect.isawaitable(arg) else arg for arg in args]
        resolved_kwargs = {key: await value if inspect.isawaitable(value) else value for key, value in kwargs.items()}

        sqlalchemy_get_or_create = getattr(cls._meta, "sqlalchemy_get_or_create", False)
        if sqlalchemy_get_or_create:
            key_fields = {}
            for field in sqlalchemy_get_or_create:  # type: ignore
                if field not in resolved_kwargs:
                    raise factory.errors.FactoryError(
                        f"sqlalchemy_get_or_create - Unable to find initialization value for '{field}' in factory {cls.__name__}"
                    )
                key_fields[field] = resolved_kwargs.pop(field)

            obj = session.query(model_class).filter_by(*resolved_args, **key_fields).one_or_none()
            if not obj:
                try:
                    obj = await cls._save(
                        model_class,
                        session,
                        tuple(resolved_args),
                        {**key_fields, **resolved_kwargs},
                    )
                except Exception:
                    await session.rollback()
                    raise

            return obj

        return await cls._save(model_class, session, tuple(resolved_args), resolved_kwargs)

    @classmethod
    async def _save(cls, model_class, session, args, kwargs):
        session_persistence = getattr(cls._meta, "sqlalchemy_session_persistence", None)

        obj = model_class(*args, **kwargs)

        session.add(obj)

        if session_persistence == SESSION_PERSISTENCE_FLUSH:
            await session.flush()
        elif session_persistence == SESSION_PERSISTENCE_COMMIT:
            await session.commit()

        return obj
