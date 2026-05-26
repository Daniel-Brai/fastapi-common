from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Path, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

from lib.attachments.schemas import AttachmentConfirmRequest, AttachmentPresignRequest


def base_router() -> APIRouter:
    r = APIRouter()

    @r.get(
        "/serve/{storage}/{file_id}",
        operation_id="serve_file",
        status_code=status.HTTP_200_OK,
    )
    async def serve_file(
        storage: Annotated[str, Path(..., description="The storage location of the file.")],
        file_id: Annotated[str, Path(..., description="The unique identifier of the file to serve.")],
    ) -> FileResponse | RedirectResponse | StreamingResponse:
        """
        Serve a stored file.
        """

        from libcloud.storage.drivers.local import LocalStorageDriver
        from sqlalchemy_file.storage import StorageManager

        try:
            file = StorageManager.get_file(f"{storage}/{file_id}")
        except Exception:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

        cdn_url = file.get_cdn_url()
        if isinstance(file.object.driver, LocalStorageDriver):
            if cdn_url is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid file path.",
                )
            return FileResponse(
                cdn_url,
                media_type=file.content_type,
                filename=file.filename,
            )

        if cdn_url:
            return RedirectResponse(cdn_url)

        return StreamingResponse(
            file.object.as_stream(),
            media_type=file.content_type,
            headers={"Content-Disposition": f'attachment;filename="{file.filename}"'},
        )

    @r.post(
        "/presign",
        operation_id="presign_upload",
        status_code=status.HTTP_200_OK,
        responses={
            status.HTTP_200_OK: {
                "description": "Presigned URLs generated successfully.",
                "content": {
                    "application/json": {
                        "example": {
                            "results": [
                                {
                                    "filename": "example.jpg",
                                    "url": "https://storage-service.com/presigned-url",
                                    "fields": {
                                        "key": "attachments/example.jpg",
                                        "AWSAccessKeyId": "AKIA...",
                                        "policy": "base64-encoded-policy",
                                        "signature": "signature",
                                    },
                                }
                            ],
                            "errors": [
                                {
                                    "filename": "invalid-file.txt",
                                    "error": "Error message describing the issue.",
                                }
                            ],
                        }
                    }
                },
            }
        },
    )
    async def presign_upload(
        req: Annotated[AttachmentPresignRequest, Body(..., description="List of files to presign.")]
    ) -> dict:
        """
        Upload files using presigned URLs
        """

        from lib.attachments.upload import PresignedUpload

        results, errors = [], []
        for item in req.files:
            try:
                creds = PresignedUpload.generate(
                    filename=item.filename,
                    content_type=item.content_type,
                    storage=item.storage,
                    expires_in=item.expires_in,
                )
                results.append({"filename": item.filename, **creds})
            except (ValueError, NotImplementedError) as exc:
                errors.append({"filename": item.filename, "error": str(exc)})

        return {"results": results, "errors": errors}

    @r.post(
        "/confirm",
        operation_id="confirm_upload",
        status_code=status.HTTP_200_OK,
        responses={
            status.HTTP_200_OK: {
                "description": "Files confirmed successfully.",
                "content": {
                    "application/json": {
                        "example": {
                            "results": [
                                {
                                    "key": "attachments/example.jpg",
                                    "file": {
                                        "id": 1,
                                        "filename": "example.jpg",
                                        "content_type": "image/jpeg",
                                        "size": 102400,
                                        "storage": "s3",
                                        "url": "https://storage-service.com/attachments/example.jpg",
                                    },
                                }
                            ],
                            "errors": [
                                {
                                    "key": "attachments/invalid-file.txt",
                                    "error": "Error message describing the issue.",
                                }
                            ],
                        }
                    }
                },
            }
        },
    )
    async def confirm_upload(
        req: Annotated[AttachmentConfirmRequest, Body(..., description="List of files to confirm.")]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Confirm uploaded files and create database records for them.
        """

        from lib.attachments.upload import PresignedUpload

        results, errors = [], []
        for item in req.files:
            try:
                file = PresignedUpload.confirm(key=item.key, storage=item.storage)
                results.append({"key": item.key, "file": dict(file)})
            except FileNotFoundError as exc:
                errors.append({"key": item.key, "error": str(exc)})

        return {"results": results, "errors": errors}

    return r
