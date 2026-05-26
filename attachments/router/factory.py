from fastapi import APIRouter

from .routes import base_router


def get_attachments_router(
    prefix: str = "/attachments",
) -> APIRouter:
    """
    Build and return the unified attachments APIRouter.

    Always included:
        GET  {prefix}/serve/{storage}/{file_id}:  serve a stored file
        POST {prefix}/presign                  :  batch presigned URL generation
        POST {prefix}/confirm                  :  batch upload confirmation
    """

    attachments_router = APIRouter(prefix=prefix.rstrip("/"), tags=["attachments"])

    attachments_router.include_router(base_router())

    return attachments_router
