from typing import Annotated, Any, Callable, cast

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import PositiveInt
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sse_starlette.sse import EventSourceResponse

from lib.ext.fastapi import IBaseResponse, IResponse, ORJSONResponse, build_orjson_response
from lib.logger import get_logger
from lib.notifications.helpers import get_own_record, serialise_record
from lib.notifications.schemas import (
    AllNotificationsResponse,
    DeletePushSubscriptionRequest,
    InboxResponse,
    MarkAllReadResponse,
    MarkReadResponse,
    OkResponse,
    PushSubscriptionOut,
    RegisterPushSubscriptionRequest,
)
from lib.notifications.services import PushSubscriptionService

logger = get_logger("lib.notifications.router.routes")


def get_notifications_router(
    *,
    auth_dep: Callable,
    get_session: Callable | None = None,
    page_size: PositiveInt = 25,
) -> APIRouter:
    """
    Build and return a pre-built notifications FastAPI router.

    This router includes inbox endpoints and a real-time SSE stream.

    Mount with:

        from lib.notifications.router import make_notifications_router
        from lib.auth import make_auth_dependency, get_backend

        app.include_router(
            get_notifications_router(auth_dep=make_auth_dependency(get_backend())),
        )


    Endpoints:

        GET  /notifications/stream         SSE stream (requires SSETransport) (Authenticated)
        GET  /notifications                Inbox — unread, paginated (Authenticated)
        GET  /notifications/all            All (including read), paginated (Authenticated)
        POST /notifications/{id}/read      Mark one as read (Authenticated)
        POST /notifications/read-all       Mark all unread as read (Authenticated)
        POST /notifications/{id}/archive   Archive one (Authenticated)
        POST /notifications/push          Register a push subscription (Authenticated)
        PATCH /notifications/push         Unregister a push subscription (Authenticated)

    Note: The router prefix comes from the configure_notifications() config,

    Parameters
    ----------
    auth_dep
        FastAPI dependency that returns the current authenticated user.
        The returned user must have an ``id`` attribute.
    get_session
        Optional dependency that yields a SQLModel/SQLAlchemy session.
        If None, the router opens its own session from the registry engine.
    page_size
        Default page size for paginated inbox endpoints.
    """

    from lib.notifications.config import get_router_prefix

    prefix = get_router_prefix()

    router = APIRouter(tags=["Notifications"], prefix=prefix)

    async def _get_session_internal():
        from sqlmodel import Session

        from lib.notifications.config import get_registry

        engine = get_registry().engine
        if engine is None:
            raise RuntimeError("Notifications router requires an engine. " "Pass engine= to configure_notifications().")

        if isinstance(engine, AsyncEngine):
            async_session = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with async_session() as session:
                yield session
        else:
            with Session(engine) as session:
                yield session

    session_dep = get_session or _get_session_internal

    @router.get(
        "/stream",
        summary="Real-time notification stream (SSE)",
        operation_id="notification_stream",
        response_class=EventSourceResponse,
        status_code=status.HTTP_200_OK,
    )
    async def notification_stream(
        user: Any = Depends(auth_dep),
    ) -> EventSourceResponse:
        """
        Stream notifications using Server-Sent Events (SSE).

        Event format:
        - Notification payloads are emitted as: ``data: <json>\n\n``
        - Keep-alive heartbeats are emitted as: ``: ping\n\n``
        """

        from lib.notifications.config import get_registry
        from lib.notifications.utils import subscribe_sse

        registry = get_registry()
        emitter = registry.event_emitter
        
        if emitter is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Notification stream unavailable: no event emitter configured or available.",
            )

        return EventSourceResponse(
            subscribe_sse(user.id, emitter),
            ping=30,
            headers={"X-Accel-Buffering": "no"},
        )

    @router.get(
        "",
        summary="Unread notification inbox",
        description="Returns unread, non-archived notifications, newest first.",
        operation_id="get_inbox",
        response_model=IResponse[InboxResponse, None],
        status_code=status.HTTP_200_OK,
    )
    async def inbox(
        page: int = 1,
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:

        from sqlmodel import func, select

        from lib.notifications.models.notification import Notification

        base_filter = (
            (Notification.recipient_type == type(user).__name__)
            & (Notification.recipient_id == str(user.id))
            & (Notification.read_at == None)  # noqa: E711
            & (Notification.archived_at == None)  # noqa: E711
        )
        total_stmt = select(func.count()).select_from(Notification).where(base_filter)
        records_stmt = (
            select(Notification)
            .where(base_filter)
            .order_by(cast(Any, Notification.created_at).desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        if isinstance(session, AsyncSession):
            total = (await session.exec(total_stmt)).one()
            records = (await session.exec(records_stmt)).all()
        else:
            total = session.exec(total_stmt).one()
            records = session.exec(records_stmt).all()

        return build_orjson_response(
            message="Inbox retrieved successfully",
            data=InboxResponse(
                notifications=[serialise_record(r) for r in records],
                unread_count=total,
                page=page,
                pages=max(1, (total + page_size - 1) // page_size),
            ),
        )

    @router.get(
        "/all",
        summary="All notifications (including read)",
        description="Returns all non-archived notifications, newest first.",
        operation_id="get_all_notifications",
        status_code=status.HTTP_200_OK,
        response_model=IResponse[AllNotificationsResponse, None],
    )
    async def all_notifications(
        page: int = 1,
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:
        from sqlmodel import func, select

        from lib.notifications.models.notification import Notification

        base_filter = (
            (Notification.recipient_type == type(user).__name__)
            & (Notification.recipient_id == str(user.id))
            & (Notification.archived_at == None)  # noqa: E711
        )
        total_stmt = select(func.count()).select_from(Notification).where(base_filter)
        records_stmt = (
            select(Notification)
            .where(base_filter)
            .order_by(cast(Any, Notification.created_at).desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        if isinstance(session, AsyncSession):
            total = (await session.exec(total_stmt)).one()
            records = (await session.exec(records_stmt)).all()
        else:
            total = session.exec(total_stmt).one()
            records = session.exec(records_stmt).all()

        return build_orjson_response(
            message="All notifications retrieved successfully",
            data=AllNotificationsResponse(
                notifications=[serialise_record(r) for r in records],
                total=total,
                page=page,
                pages=max(1, (total + page_size - 1) // page_size),
            ),
        )

    @router.post(
        "/{notification_id}/read",
        summary="Mark notification as read",
        operation_id="mark_notification_read",
        status_code=status.HTTP_200_OK,
        response_model=IResponse[MarkReadResponse, None],
    )
    async def mark_read(
        notification_id: int,
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:
        record = await get_own_record(notification_id, user, session)

        if record is None:
            return build_orjson_response(
                message="Notification not found or access denied",
                data=MarkReadResponse(ok=False),
            )

        await record.mark_read(session)

        return build_orjson_response(
            message="Notification marked as read",
            data=MarkReadResponse(ok=True),
        )

    @router.post(
        "/read-all",
        summary="Mark all unread notifications as read",
        operation_id="mark_all_notifications_read",
        status_code=status.HTTP_200_OK,
        response_model=IResponse[MarkAllReadResponse, None],
    )
    async def mark_all_read(
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:
        from datetime import datetime

        from sqlmodel import select

        from lib.notifications.models.notification import Notification

        unread_stmt = (
            select(Notification)
            .where(Notification.recipient_type == type(user).__name__)
            .where(Notification.recipient_id == str(user.id))
            .where(Notification.read_at == None)  # noqa: E711
        )

        if isinstance(session, AsyncSession):
            unread = (await session.exec(unread_stmt)).all()
        else:
            unread = session.exec(unread_stmt).all()

        now = datetime.utcnow()
        for rec in unread:
            rec.read_at = now
            session.add(rec)

        if isinstance(session, AsyncSession):
            await session.commit()
        else:
            session.commit()

        return build_orjson_response(
            message="All notifications marked as read",
            data=MarkAllReadResponse(ok=True, marked=len(unread)),
        )

    @router.post(
        "/{notification_id}/archive",
        summary="Archive a notification",
        operation_id="archive_notification",
        status_code=status.HTTP_200_OK,
        response_model=IResponse[OkResponse, None],
    )
    async def archive(
        notification_id: int,
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:
        record = await get_own_record(notification_id, user, session)
        if record is None:
            return build_orjson_response(
                message="Notification not found or access denied",
                data=OkResponse(ok=False),
            )

        await record.archive(session)

        return build_orjson_response(
            message="Notification archived successfully",
            data=OkResponse(ok=True),
        )

    @router.post(
        "/push",
        summary="Register a push subscription",
        operation_id="register_push_subscription",
        response_model=IResponse[PushSubscriptionOut, None],
        status_code=status.HTTP_200_OK,
    )
    async def register_push_subscription(
        body: Annotated[
            RegisterPushSubscriptionRequest,
            Body(
                ...,
                description="The data to register a new push subscription, including the endpoint and cryptographic keys.",
            ),
        ],
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:
        service = PushSubscriptionService(session)
        subscription = await service.register(
            user_id=user.id,
            endpoint=str(body.endpoint),
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
        )
        return build_orjson_response(
            message="Push subscription registered successfully",
            data=PushSubscriptionOut.from_model(subscription),
        )

    @router.patch(
        "/push",
        summary="Unregister a push subscription",
        operation_id="unregister_push_subscription",
        response_model=IBaseResponse,
        status_code=status.HTTP_200_OK,
    )
    async def unregister_push_subscription(
        body: Annotated[
            DeletePushSubscriptionRequest,
            Body(..., description="The data to unregister a push subscription, including the endpoint."),
        ],
        user: Any = Depends(auth_dep),
        session: Any = Depends(session_dep),
    ) -> ORJSONResponse:
        service = PushSubscriptionService(session)
        await service.unregister(
            user_id=user.id,
            endpoint=str(body.endpoint),
        )

        return build_orjson_response(
            message="Push subscription unregistered successfully",
        )

    return router
