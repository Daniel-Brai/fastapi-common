import inspect
from typing import Callable

from fastapi import Request
from starlette.types import ASGIApp

from lib.audit.context import set_auditor, set_remote_addr, set_request_id
from lib.ext.fastapi import get_client_ip, get_request_id
from lib.logger import get_logger

logger = get_logger("lib.audit.middleware")


class AuditMiddleware:
    """
    FastAPI integration — two ways to set the current auditor and request context:

    1. AuditMiddleware (recommended)
       Starlette ASGI middleware that runs on every request.

       Automatically sets:
         • request_id: new id per request or from X-Request-ID header
         • remote_address: client IP
         • auditor: resolved via the provided user_loader callable

       Usage:

        ```python
           from lib.audit.middleware import AuditMiddleware
           from lib.auth             import get_backend, make_auth_dependency

           # user_loader receives the raw Request and must return a user or None.
           # It may be async or sync.
           async def load_user(request: Request):
               try:
                   return await make_auth_dependency(get_backend())(request)
               except Exception:
                   return None

           app.add_middleware(AuditMiddleware, user_loader=load_user)
        ```

    2. set_auditor FastAPI dependency
       Use when you only need to set the auditor for specific routes,
       or when using the auth library's :meth:`~lib.auth.dependencies.get_current_user` dependency.

       Usage:

        ```python
           from lib.audit.dependencies import AuditingDepends

           @router.post("/posts")
           async def create_post(
               body: PostCreate,
               user = Depends(make_auth_dependency(get_backend())),        # require_auth
               _    = Depends(AuditingDepends),   # sets auditor + uuid
           ):
               ...

           # Or combine:
           @router.post("/posts")
           async def create_post(
               body: PostCreate,
               user = Depends(make_audit_dependency(make_auth_dependency(get_backend()))),        # require_auth + set_auditor
           ):
               ...
        ```

    Parameters
    ----------
    app
        The ASGI application (passed automatically by add_middleware).
    user_loader
        async or sync callable(request: Request) → user | None.
        Called once per request.  Exceptions are caught and logged — on
        failure the auditor is set to None (system/anonymous).
    """

    def __init__(self, app: ASGIApp, *, user_loader: Callable) -> None:
        self.app = app
        self._user_loader = user_loader

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http":
            request = Request(scope, receive=receive)

            set_request_id(get_request_id(request))
            set_remote_addr(get_client_ip(request))

            user = None
            try:
                loader = self._user_loader
                if inspect.iscoroutinefunction(loader):
                    user = await loader(request)
                else:
                    user = loader(request)
            except Exception:
                logger.debug(
                    "AuditMiddleware: user_loader raised, auditor set to None",
                    exc_info=True,
                )

            set_auditor(user)

        await self.app(scope, receive, send)
