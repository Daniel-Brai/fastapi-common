import functools
import inspect
import time
from collections.abc import Sequence
from enum import Enum
from typing import Any, Callable, ClassVar, TypeVar

import inflection
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi import params as fastapi_params
from fastapi import status
from fastapi.datastructures import Default
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.routing import APIRoute
from fastapi.types import IncEx
from fastapi.utils import generate_unique_id
from starlette.routing import BaseRoute
from starlette_async_jinja import AsyncJinja2Templates

from lib.ext.fastapi.responses import ORJSONResponse, build_orjson_response
from lib.logger import get_logger
from lib.templates import TemplateEngine

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

type TemplateRenderCallback = Callable[[str, float], Any]


class _RouteDefinition:
    """
    A class that is stored on a method as ``__route__`` by the @get / @post / … decorators.

    It is collected by `ControllerMeta` at class creation time.
    """

    def __init__(self, path: str, methods: list[str], **kwargs: Any) -> None:
        self.path: str = path
        self.methods: list[str] = methods
        self.kwargs: dict[str, Any] = kwargs
        self.before_actions: list[str] = []  # populated by ControllerMeta


class _BeforeActionMarker:
    """
    A class that is stored on a method as ``__before_action__`` by the @before_action decorator.

    It describes which route methods this hook gates.
    """

    __slots__ = ("only", "exclude")

    def __init__(
        self,
        only: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> None:
        self.only: list[str] | None = only
        self.exclude: list[str] | None = exclude


_ROUTE_ATTR = "__route__"
_BEFORE_ATTR = "__before_action__"


def get(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a GET route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.get` exactly with the exception of using a
    custom ``response_class`` default that works better with typical API responses.

    Example::

        @get("/", response_model=list[PostOut], status_code=200)
        async def index(self, request: Request) -> list[PostOut]: ...

        @get("/{post_id}", summary="Fetch one post", tags=["posts"])
        async def show(
            self,
            request: Request,
            post_id: Annotated[
                PostiveInt,
                Path(..., description="The ID of the post to retrieve")
            ]
        ) -> PostOut: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["GET"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def post(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a POST route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.post` exactly.

    Example::

        @post("/", status_code=201, response_model=PostOut)
        async def create(
            self,
            request: Request,
            body: Annotated[PostCreate, Body(..., description="The post to create")]
        ) -> PostOut: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["POST"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def put(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a PUT route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.put` exactly.

    Example::

        @put("/{post_id}", response_model=PostOut)
        async def update(self, request: Request, post_id: int, body: PostUpdate) -> PostOut: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["PUT"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def patch(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a PATCH route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.patch` exactly.

    Example::

        @patch("/{post_id}", response_model=PostOut)
        async def partial_update(self, request: Request, post_id: int, body: PostPatch) -> PostOut: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["PATCH"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def head(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a HEAD route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.head` exactly.

    Example::

        @head("/", response_model=IResponse[dict[str, Any], None])
        async def head(self, request: Request) -> ORJSONResponse: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["HEAD"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def options(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare an OPTIONS route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.options` exactly.

    Example::

        @options("/", response_model=IResponse[dict[str, Any], None])
        async def options(self, request: Request) -> ORJSONResponse: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["OPTIONS"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def trace(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a TRACE route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.trace` exactly.

    Example::

        @trace("/", response_model=IResponse[dict[str, Any], None])
        async def trace(self, request: Request) -> ORJSONResponse: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["TRACE"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def delete(
    path: str = "/",
    *,
    response_model: Any = Default(None),
    status_code: int | None = status.HTTP_200_OK,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[fastapi_params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: IncEx | None = None,
    response_model_exclude: IncEx | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = Default(ORJSONResponse),  # type: ignore[assignment]
    name: str | None = None,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),  # type: ignore[assignment]
) -> Callable[[F], F]:
    """
    Declare a DELETE route on a :class:`Controller` method.

    Parameters mirror :meth:`fastapi.APIRouter.delete` exactly.

    Example::

        @delete("/{post_id}", status_code=204)
        async def destroy(self, request: Request, post_id: int) -> None: ...
    """

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ROUTE_ATTR,
            _RouteDefinition(
                path,
                ["DELETE"],
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                response_description=response_description,
                responses=responses,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                name=name,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )
        return fn

    return decorator


def before_action(
    fn_or_only: Any = None,
    *,
    only: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Any:
    """
    Mark a controller method as a before-action hook.

    Parameters declared on before_action methods including ``Annotated``
    ``Depends()`` are automatically merged into the route handler's
    signature so FastAPI injects them.  Instance attributes set inside a
    before_action (``self.user = user``) are immediately available to the
    main handler and to subsequent before_actions on the same request.

    Usage::

        class PostsController(Controller):
            prefix = "/posts"

            # Runs before every route — inject a dependency and store it.
            @before_action
            async def authenticate(
                self, user: Annotated[AuthUserMixin, Depends(make_auth_dependency(get_backend()))]
            ):
                self.user = user

            # Runs only before the named route methods.
            @before_action(only=["create", "update", "destroy"])
            async def require_admin(self):
                if not self.user.is_admin():
                    self.abort(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

            # Runs before every route EXCEPT the named ones.
            @before_action(exclude=["index", "show"])
            async def check_verified(self):
                if not self.user.email_verified:
                    self.abort(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

            @get("/")
            async def index(self, request: Request) -> HTMLResponse:
                return await self.render("posts/index.html", request)

            @post("/new")
            async def create(self, request: Request) -> HTMLResponse:
                return await self.render("posts/new.html", request)

            @get("/{post_id}")
            async def show(self, request: Request, post_id: int) -> HTMLResponse:
                return await self.render("posts/show.html", request, post_id=post_id)

            @patch("/{post_id}/edit")
            async def edit(self, request: Request, post_id: int) -> HTMLResponse:
                return await self.render("posts/edit.html", request, post_id=post_id)

            @delete("/{post_id}")
            async def destroy(self, request: Request, post_id: int) -> RedirectResponse:
                # Call any service method to delete the post here,
                # e.g. await PostService.delete_post(post_id)

                # Or use dependencies to inject a service instance and call it:
                # @delete("/{post_id}")
                # async def destroy(self, request: Request, post_id: int, post_service: PostService = Depends()):
                #     await post_service.delete_post(post_id)

                return self.redirect("/posts")


    Short-circuit behaviour:

    * Raise ``HTTPException`` to abort with an error response.
    * Return a ``Response`` object to return it directly (bypasses the route).
    * Return ``None`` (or nothing) to continue normally.

    Parameters
    ----------
    only
        Whitelist of route method names this hook runs before.
        Mutually exclusive with ``exclude``.
    exclude
        Blacklist of route method names this hook does NOT run before.
        Mutually exclusive with ``only``.
    """

    # @before_action  (no parentheses, fn_or_only IS the decorated function)
    if callable(fn_or_only):
        setattr(fn_or_only, _BEFORE_ATTR, _BeforeActionMarker())
        return fn_or_only

    # @before_action(only=[...])  or  @before_action(exclude=[...])
    resolved_only = fn_or_only if isinstance(fn_or_only, list) else only
    resolved_exclude = exclude

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(
            fn,
            _BEFORE_ATTR,
            _BeforeActionMarker(
                only=resolved_only,
                exclude=resolved_exclude,
            ),
        )
        return fn

    return decorator


class ControllerMeta(type):
    """
    Metaclass that introspects the class body at definition time and:

    1. Collects every ``@get / @post / …`` decorated method into
       ``cls._route_definitions``.
    2. Collects every ``@before_action`` decorated method into
       ``cls._before_action_definitions``.
    3. Pre-computes which before_action hooks run before each route and stores
       that list on ``_RouteDefinition.before_actions``.

    Attributes are injected via ``setattr``(the metaclass instance type has no
    statically-declared ``_route_definitions`` attribute).
    """

    _route_definitions: dict[str, _RouteDefinition] = {}
    _before_action_definitions: dict[str, _BeforeActionMarker] = {}

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "ControllerMeta":
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        route_defs: dict[str, _RouteDefinition] = {}
        before_defs: dict[str, _BeforeActionMarker] = {}

        for klass in reversed(cls.__mro__):
            for attr_name, attr_val in vars(klass).items():
                route_marker = getattr(attr_val, _ROUTE_ATTR, None)
                if isinstance(route_marker, _RouteDefinition):
                    route_defs[attr_name] = route_marker

                before_marker = getattr(attr_val, _BEFORE_ATTR, None)
                if isinstance(before_marker, _BeforeActionMarker):
                    before_defs[attr_name] = before_marker

        cls._route_definitions = route_defs
        cls._before_action_definitions = before_defs

        for route_name, route_def in route_defs.items():
            applicable: list[str] = []
            for ba_name, ba_marker in before_defs.items():
                if ba_marker.only is not None:
                    if route_name in ba_marker.only:
                        applicable.append(ba_name)
                elif ba_marker.exclude is not None:
                    if route_name not in ba_marker.exclude:
                        applicable.append(ba_name)
                else:
                    # No only/exclude, applies to every route.
                    applicable.append(ba_name)
            route_def.before_actions = applicable

        return cls


class Controller(metaclass=ControllerMeta):
    """
    Base class for class-based HTTP controllers.

    The ``Controller`` provides a structured way to define routes, lifecycle
    hooks, and response helpers for applications built with FastAPI.

    Controllers group related HTTP endpoints into a single class while keeping
    request logic, authorization hooks, and rendering utilities close together.

    Routes are declared using decorators such as ``@get`` or ``@post`` on class
    methods. During class creation the ``ControllerMeta`` metaclass inspects the
    class body and automatically registers these methods as route handlers.

    --------------------------------------------------------------------------
    Class Attributes
    --------------------------------------------------------------------------

    prefix : str
        URL prefix applied to all routes defined in the controller.

        Example::

            class PostsController(Controller):
                prefix = "/posts"

    tags : list[str]
        OpenAPI tags applied to all routes. If not specified, a default tag
        is derived from the controller class name.

        Example::

            class PostsController(Controller):
                tags = ["Posts"]

    dependencies : list
        Global FastAPI dependencies applied to every route in this controller.

        Example::

            dependencies = [Depends(require_auth)]

    responses : dict
        Additional OpenAPI response metadata applied to all routes.

        Example::

            responses = {
                401: {"description": "Unauthorized"},
                403: {"description": "Forbidden"},
            }

    include_in_schema : bool
        Whether routes defined in this controller should appear in the
        generated OpenAPI documentation.

        Default: ``True``


    --------------------------------------------------------------------------
    Routing
    --------------------------------------------------------------------------

    Routes are declared using HTTP decorators:

    - ``@get(path)``
    - ``@post(path)``
    - ``@put(path)``
    - ``@patch(path)``
    - ``@delete(path)``
    - ``@head(path)``
    - ``@options(path)``
    - ``@trace(path)``

    Example::

        class PostsController(Controller):

            prefix = "/posts"

            @get("/")
            async def index(self, request: Request):
                return self.json("Posts retrieved")

            @get(
                "/{post_id}",
                operation_id="get_post",
                summary="Get a single post",
                description="Retrieve a post using its unique identifier.",
                status_code=status.HTTP_200_OK,
                response_model=IResponse[dict[str, Any], None],
            )
            async def show(
                self,
                request: Request,
                post_id: Annotated[PositiveInt, Path(..., description="The ID of the post to retrieve")]
            ) -> ORJSONResponse:
                return self.json("Post retrieved", {"id": post_id})


    Controllers are mounted into the application using::

        app.include_router(PostsController.as_router())


    --------------------------------------------------------------------------
    Before Actions
    --------------------------------------------------------------------------

    ``before_action`` methods allow executing logic before a route handler runs.
    They are useful for authentication, permission checks, and request setup.

    Hooks can apply to:

    - all routes
    - specific routes
    - all except certain routes

    Example::

        class AdminController(Controller):

            prefix = "/admin"

            @before_action
            async def require_admin(self, request: Request):
                user = await make_auth_dependency(get_backend())(request)
                if not user.is_admin:
                    self.abort(status.HTTP_403_FORBIDDEN, "Admin access required")

            @before_action(only=["destroy"])
            async def confirm_password(self, request: Request):
                ...


    --------------------------------------------------------------------------
    Response Helpers
    --------------------------------------------------------------------------

    The controller provides several helper methods to simplify returning
    HTTP responses.

    json(...)
        Return a structured JSON response using ORJSON.

    render(...)
        Render a template using the configured template engine.

    render_fragment(...)
        Render a named template fragment (useful for HTMX partial updates).

    render_macro(...)
        Render a Jinja2 macro directly from a template module.

    redirect(...)
        Return an HTTP redirect response.

    no_content()
        Return an empty ``204 No Content`` response.

    abort(status_code, detail)
        Raise an HTTPException immediately.


    --------------------------------------------------------------------------
    Template Rendering
    --------------------------------------------------------------------------

    Templates must be configured at application startup using::

        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="templates")

        configure_controllers(templates=templates)

    Both synchronous and asynchronous template engines are supported.


    Example::

        @get("/")
        async def index(self, request: Request):
            posts = get_posts()
            return await self.render(
                "posts/index.html",
                request,
                posts=posts
            )


    Fragment rendering (useful with HTMX)::

        @get("/header")
        async def header(self, request: Request):
            return await self.render_fragment(
                "layout.html",
                "header",
                site_name="My Site"
            )


    Macro rendering::

        html = await self.render_macro(
            "components.html",
            "alert",
            "success",
            "Post created"
        )


    --------------------------------------------------------------------------
    Lifecycle
    --------------------------------------------------------------------------

    For each request:

    1. The controller instance is created.
    2. Applicable ``before_action`` hooks execute.
    3. The route method executes.
    4. The returned response is sent to the client.


    --------------------------------------------------------------------------
    Example
    --------------------------------------------------------------------------

    Minimal controller example::

        class PostsController(Controller):

            prefix = "/posts"

            @get("/")
            async def index(self, request: Request):
                return self.json("Posts retrieved")

            @post("/")
            async def create(self, request: Request):
                return self.json("Post created", status_code=status.HTTP_201_CREATED)

    Mount the controller::

        app.include_router(PostsController.as_router())


    --------------------------------------------------------------------------
    Notes
    --------------------------------------------------------------------------

    - Controllers are stateless and instantiated per request.
    - All FastAPI dependencies remain fully supported.
    - Route methods may be synchronous or asynchronous.
    - Template rendering helpers require templates to be configured.
    """

    prefix: str = ""
    tags: list[str] = []
    dependencies: list[Any] = []
    responses: dict[Any, Any] = {}
    include_in_schema: bool = True

    # Metaclass-injected attributes
    # ControllerMeta.__new__ populates them via setattr for every
    # class in the hierarchy (including Controller itself with empty dicts).
    _route_definitions: ClassVar[dict[str, _RouteDefinition]]
    _before_action_definitions: ClassVar[dict[str, _BeforeActionMarker]]

    # Shared Jinja2Templates instance set via Controller.set_templates()
    _templates: ClassVar[TemplateEngine | None] = None
    _template_render_callback: ClassVar[TemplateRenderCallback | None] = None

    async def _run_template_render_callback(
        self,
        template: str,
        duration: float,
    ) -> None:
        callback = type(self)._template_render_callback
        if callback is None:
            return

        result = callback(template, duration)
        if inspect.isawaitable(result):
            await result

    @classmethod
    def _filtered_route_items(
        cls,
        only: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> list[tuple[str, _RouteDefinition]]:
        if only is not None and exclude is not None:
            raise ValueError("only and exclude are mutually exclusive")

        route_names = set(cls._route_definitions)
        if only is not None:
            unknown = set(only) - route_names
            if unknown:
                raise ValueError(f"Unknown route names in only: {sorted(unknown)}")
            return [(name, rd) for name, rd in cls._route_definitions.items() if name in set(only)]

        if exclude is not None:
            unknown = set(exclude) - route_names
            if unknown:
                raise ValueError(f"Unknown route names in exclude: {sorted(unknown)}")
            return [(name, rd) for name, rd in cls._route_definitions.items() if name not in set(exclude)]

        return list(cls._route_definitions.items())

    @classmethod
    def as_router(cls, only: list[str] | None = None, exclude: list[str] | None = None) -> APIRouter:
        """
        Build and return a ``FastAPI`` ``APIRouter`` for this controller.

        Mount with::

            app.include_router(PostsController.as_router())
        """

        # Derive default tags from the class name: PostsController becomes ["Posts"], if not explicitly set.
        default_tags: list[Any] = cls.tags or [
            inflection.titleize(inflection.pluralize(cls.__name__.replace("Controller", "").lower()))
        ]

        r = APIRouter(
            prefix=cls.prefix,
            tags=default_tags,
            dependencies=cls.dependencies,
            responses=cls.responses,
            include_in_schema=cls.include_in_schema,
        )

        def _route_sort_key(item: tuple[str, _RouteDefinition]) -> tuple[int, int, int]:
            _, route_def = item
            path = route_def.path.lstrip("/")
            segments = path.split("/") if path else []
            param_count = sum(1 for segment in segments if segment.startswith("{"))
            static_count = len(segments) - param_count
            return (param_count, -static_count, len(segments))

        for method_name, route_def in sorted(
            cls._filtered_route_items(only=only, exclude=exclude),
            key=_route_sort_key,
        ):
            handler = cls._build_handler(method_name, route_def)
            r.add_api_route(
                route_def.path,
                handler,
                methods=route_def.methods,
                **route_def.kwargs,
            )
            logger.debug(
                "Controller: registered %s %s%s → %s.%s",
                "/".join(route_def.methods),
                cls.prefix,
                route_def.path,
                cls.__name__,
                method_name,
            )

        return r

    @classmethod
    def register(
        cls,
        app_or_router: Any,
        *,
        only: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> None:
        """
        Register this controller with a FastAPI application or router.

        Example::

            app = FastAPI()

            # Includes the controller's router into the app
            PostsController.register(app)

            # Include only the `index` route from PostsController:
            PostsController.register(app, only=["index"])

            router = APIRouter()

            # Includes the controller's router into an existing router
            CommentsController.register(router)

            app.include_router(router)
        """

        if not isinstance(app_or_router, (FastAPI, APIRouter)):
            raise TypeError("Expected FastAPI or APIRouter instance")

        app_or_router.include_router(cls.as_router(only=only, exclude=exclude))

    @classmethod
    def _build_handler(
        cls,
        method_name: str,
        route_def: _RouteDefinition,
    ) -> Callable[..., Any]:
        """
        Wrap a controller method into a plain ``async def`` that FastAPI can
        register as a route.

        The wrapper:
        1. Instantiates the controller once per request.
        2. Runs each applicable before_action in definition order, forwarding
           only the kwargs that the hook declares.
        3. Calls the main method and returns its result.

        ``__signature__`` is rewritten (via ``object.__setattr__``) so FastAPI
        reads the correct parameters for dependency injection.  Direct
        assignment (``handler.__signature__ = …``) because ``functools.wraps`` returns a
        typed wrapper whose ``__signature__`` attribute is not recognised as
        settable.
        """

        original_method = getattr(cls, method_name)
        before_names = route_def.before_actions

        main_sig = inspect.signature(original_method)

        # Collect params from the main method first (they take priority on
        # name collisions), then add any extra params from before_actions.
        merged_params: dict[str, inspect.Parameter] = {
            name: param for name, param in main_sig.parameters.items() if name != "self"
        }

        for ba_name in before_names:
            ba_method = getattr(cls, ba_name)
            ba_sig = inspect.signature(ba_method)
            for name, param in ba_sig.parameters.items():
                if name != "self" and name not in merged_params:
                    merged_params[name] = param

        # Signature validation requires that parameters without
        # defaults precede parameters with defaults.  After merging across
        # methods this invariant can be violated (e.g. a main-method param
        # with a default ends up before a before_action param with no
        # default).  Re-sort: params without defaults first, then those
        # with defaults.  FastAPI cares only about names and annotations
        # when resolving Depends(), so the position change is harmless.
        def _has_default(p: inspect.Parameter) -> bool:
            return p.default is not inspect.Parameter.empty

        sorted_params = sorted(merged_params.values(), key=_has_default)

        @functools.wraps(original_method)
        async def handler(**kwargs: Any) -> Any:
            instance = cls()

            for ba_name in before_names:
                ba_method = getattr(instance, ba_name)
                ba_sig = inspect.signature(ba_method)
                # Forward only the kwargs that this before_action declares.
                ba_kwargs = {k: v for k, v in kwargs.items() if k in ba_sig.parameters}
                result: Any = ba_method(**ba_kwargs)
                if inspect.isawaitable(result):
                    result = await result
                # Return a Response directly to short-circuit the route.
                if isinstance(result, Response):
                    return result

            # Forward only the kwargs that the main method declares.
            main_kwargs = {k: v for k, v in kwargs.items() if k in main_sig.parameters and k != "self"}
            main_result: Any = original_method(instance, **main_kwargs)
            if inspect.isawaitable(main_result):
                main_result = await main_result

            return main_result

        # Rewrite __signature__ with the merged and sorted parameter set so
        # FastAPI injects all dependencies (including those from before_actions).
        merged_sig = main_sig.replace(parameters=sorted_params)
        object.__setattr__(handler, "__signature__", merged_sig)
        return handler

    def json(
        self,
        message: str,
        data: Any = None,
        metadata: Any = None,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, Any] | None = None,
    ) -> ORJSONResponse:
        """
        Return a ORJSON response.

        Accepts Pydantic/SQLModel models, plain dicts, lists, and primitives.
        Models are serialised via .model_dump() (Pydantic v2) or .dict().

        Examples:

            return self.json(post)
            return self.json({"id": post.id}, status_code=status.HTTP_201_CREATED)
            return self.json(posts)
        """

        if data is not None:
            return build_orjson_response(
                message=message,
                data=data,
                metadata=metadata,
                headers=headers,
                status_code=status_code,
            )

        return build_orjson_response(
            message=message,
            data=data,
            metadata=metadata,
            base=True,
            headers=headers,
            status_code=status_code,
        )

    async def render(
        self,
        template: str,
        request: Request,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> HTMLResponse:
        """
        Render a template using either sync or async template engines.
        """

        if self._templates is None:
            raise RuntimeError("Templates not configured. " "Call configure_controller(...) at startup.")

        ctx = {"request": request, **context}
        start_time = time.perf_counter()

        if isinstance(self._templates, AsyncJinja2Templates):
            response = await self._templates.TemplateResponse(
                request,
                template,
                ctx,
                status_code=status_code,
                headers=headers,
            )
        else:
            response = self._templates.TemplateResponse(
                name=template,
                context=ctx,
                status_code=status_code,
                headers=headers,
            )

        await self._run_template_render_callback(
            template,
            time.perf_counter() - start_time,
        )

        return response

    async def render_fragment(
        self,
        template: str,
        fragment: str,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> HTMLResponse:
        """
        Render a specific fragment block from a template.

        Requires `AsyncJinja2Templates`.
        """

        if self._templates is None:
            raise RuntimeError("Templates not configured")

        if not isinstance(self._templates, AsyncJinja2Templates):
            raise RuntimeError("render_fragment requires AsyncJinja2Templates")

        start_time = time.perf_counter()
        html = await self._templates.render_fragment(
            template,
            fragment,
            **context,
        )
        duration = time.perf_counter() - start_time

        await self._run_template_render_callback(
            template,
            duration,
        )

        return HTMLResponse(
            content=html,
            status_code=status_code,
            headers=headers,
        )

    async def render_block(
        self,
        template: str,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> HTMLResponse:
        """
        Render a template block (the entire template if no blocks defined).

        Requires `AsyncJinja2Templates`.
        """

        if self._templates is None:
            raise RuntimeError("Templates not configured")

        if not isinstance(self._templates, AsyncJinja2Templates):
            raise RuntimeError("render_block requires AsyncJinja2Templates")

        start_time = time.perf_counter()
        html = await self._templates.render_block(
            template,
            **context,
        )
        duration = time.perf_counter() - start_time

        await self._run_template_render_callback(
            template,
            duration,
        )

        return HTMLResponse(content=html, status_code=status_code, headers=headers)

    async def render_macro(
        self,
        template: str,
        macro: str,
        *args: Any,
        **kwargs: Any,
    ) -> HTMLResponse:
        """
        Render a macro from a template module.

        Requires `AsyncJinja2Templates`.
        """

        if self._templates is None:
            raise RuntimeError("Templates not configured")

        if not isinstance(self._templates, AsyncJinja2Templates):
            raise RuntimeError("Template engine not compatible")

        start_time = time.perf_counter()
        template_obj = await self._templates.env.get_template_async(template)
        module = await template_obj.make_module_async()

        macro_fn = getattr(module, macro)
        macro_html = await macro_fn(*args, **kwargs)
        duration = time.perf_counter() - start_time

        await self._run_template_render_callback(
            template,
            duration,
        )

        return HTMLResponse(content=macro_html)

    def redirect(
        self,
        url: str,
        *,
        status_code: int = status.HTTP_302_FOUND,
        headers: dict[str, str] | None = None,
    ) -> RedirectResponse:
        """
        Return a redirect response.

        Examples::

            return self.redirect("/posts")
            return self.redirect(f"/posts/{post.id}", status_code=status.HTTP_303_SEE_OTHER)
            return self.redirect("https://example.com", status_code=status.HTTP_301_MOVED_PERMANENTLY, headers={"X-Custom": "Value"})
        """

        return RedirectResponse(url=url, status_code=status_code, headers=headers)

    def text(
        self,
        content: str,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """
        Return a plain text response.
        """

        return PlainTextResponse(content, status_code=status_code, headers=headers)

    def stream(
        self,
        content: Any,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
        media_type: str = "text/plain; charset=utf-8",
    ) -> StreamingResponse:
        """
        Return a streaming response.

        Use this for large responses, server-sent events (SSE), or any scenario
        where you want to send data in chunks over time.

        The ``content`` argument can be:

        - An async generator (``async def generate(): yield chunk``)
        - A regular generator (``def generate(): yield chunk``)
        - A bytes object
        - A string
        - A file-like object

        Example usage with an async generator::

            async def event_stream():
                for i in range(10):
                    yield f"data: {i}\\n\\n"
                    await asyncio.sleep(1)

            @get("/stream")
            async def stream_events(self, request: Request):
                return self.stream(event_stream(), media_type="text/event-stream")

        Parameters
        ----------
        content
            The content to stream. Can be a generator, async generator, bytes, or string.
        status_code
            HTTP status code for the response.
        headers
            Optional additional headers to include in the response.
        media_type
            The media type (MIME type) of the response. Defaults to ``text/plain``.
        """

        return StreamingResponse(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
        )

    def no_content(self) -> Response:
        """
        Return a ``204 No Content`` response.
        """
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def raw(
        self,
        content: str | bytes,
        *,
        media_type: str,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """
        Return a bare ``Response`` with caller-controlled content and media type.

        Use this when the response body is already serialised and the framework
        should not touch it — Fever API JSON, OPML XML, iCal feeds, CSV exports,
        and similar protocol-specific payloads are the intended cases.

        The ``media_type`` parameter is required so the intent is always explicit
        at the call site.

        Examples::

            return self.raw("Hello, world!", media_type="text/plain")
        """
        return Response(
            content=content,
            status_code=status_code,
            media_type=media_type,
            headers=headers,
        )

    def abort(self, status_code: int, detail: str) -> None:
        """
        Raise an ``HTTPException`` to abort the request immediately.

        Examples::

            self.abort(status.HTTP_404_NOT_FOUND, "Post not found")
            self.abort(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        """

        raise HTTPException(status_code=status_code, detail=detail)

    @classmethod
    def set_template_engine(
        cls,
        template_engine: TemplateEngine,
        template_render_callback: TemplateRenderCallback | None = None,
    ) -> None:
        """
        Set the ``Jinja2Templates`` instance used by ``self.render()``.

        Optionally configure a callback that will be invoked after every
        template render with the template name, render duration, and render
        context.

        Use :meth:`~lib.ext.fastapi.configure_controllers` at application startup to set this globally for all controllers.

        Call once at application startup::

            from fastapi.templating import Jinja2Templates
            templates = Jinja2Templates(directory="templates")

            configure_controllers(
                templates=templates,
                template_render_callback=template_rendered,
            )
        """

        cls._templates = template_engine
        cls._template_render_callback = template_render_callback
