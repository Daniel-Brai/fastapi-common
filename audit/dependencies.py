from typing import Any, Callable

from fastapi import Depends, Request

from lib.audit.context import set_auditor, set_remote_addr, set_request_id
from lib.ext.fastapi import get_client_ip, get_request_id


def make_audit_dependency(user_dep: Callable) -> Callable:
    """
    Factory: create a combined auth + audit dependency.

    Wraps an existing auth dependency (e.g. require_auth) so that calling it
    also sets the auditor for the current request.

    Usage:

        from lib.auth import make_auth_dependency, get_backend

        audit_user = make_audit_dependency(make_auth_dependency(get_backend()))

        @router.post("/posts")
        async def create_post(user = Depends(audit_user)):
            ...  # user is authenticated AND set as the auditor
    """

    async def _combined(request: Request, user=Depends(user_dep)) -> Any:
        set_request_id(get_request_id(request))
        set_remote_addr(get_client_ip(request))
        set_auditor(user)
        return user

    import functools

    functools.update_wrapper(_combined, user_dep)
    return _combined


async def AuditingDepends(request: Request) -> None:
    """
    FastAPI dependency for auditing.

    You need to set request_uuid and remote_address for the current
    route.

    It does not set the auditor use alongside your auth dependency.

    Usage:

        @router.post("/posts")
        async def create(_, = Depends(AuditingDepends), user = Depends(make_auth_dependency(get_backend()))):
            set_auditor(user)
    """

    set_request_id(get_request_id(request))
    set_remote_addr(get_client_ip(request))
