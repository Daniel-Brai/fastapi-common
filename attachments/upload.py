import uuid
from typing import Any

from sqlalchemy_file.storage import StorageManager

from lib.attachments.file import AttachedFile
from lib.logger import get_logger

log = get_logger("lib.attachments.uploads")


class PresignedUpload:
    """
    Presigned URL generation and direct-to-storage upload confirmation
    """

    @staticmethod
    def generate(
        filename: str,
        content_type: str,
        storage: str = "default",
        expires_in: int = 3600,
    ) -> dict[str, Any]:
        """
        Generate a presigned URL for direct upload to the specified storage backend.

        Usage:
            presign = PresignedUpload.generate(
                filename=req.filename,
                content_type=req.content_type,
                storage=req.storage,
            )
            return presign
        """

        container = StorageManager._storages.get(storage)
        if container is None:
            raise ValueError(f"Storage '{storage}' is not configured.")

        driver_cls = type(container.driver).__name__

        if "S3" in driver_cls or "MinIO" in driver_cls:
            return PresignedUpload._s3_presign(container, filename, content_type, expires_in)
        if "Google" in driver_cls:
            return PresignedUpload._gcs_presign(container, filename, content_type, expires_in)

        key = f"uploads/{uuid.uuid4()}/{filename}"
        return {"type": "local", "url": "/attachments/upload", "key": key}

    @staticmethod
    def _s3_presign(container, filename, content_type, expires_in) -> dict:
        try:
            import boto3
        except ImportError:
            raise ImportError("pip install boto3")
        key = f"uploads/{uuid.uuid4()}/{filename}"
        region = getattr(container.driver, "region", None) or "us-east-1"
        resp = boto3.client("s3", region_name=region).generate_presigned_post(
            Bucket=container.name,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}],
            ExpiresIn=expires_in,
        )
        return {"type": "s3", "url": resp["url"], "fields": resp["fields"], "key": key}

    @staticmethod
    def _gcs_presign(container, filename, content_type, expires_in) -> dict:
        try:
            from google.cloud import storage as gcs  # type: ignore
        except ImportError:
            raise ImportError("pip install google-cloud-storage")

        from datetime import timedelta

        key = f"uploads/{uuid.uuid4()}/{filename}"
        blob = gcs.Client().bucket(container.name).blob(key)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expires_in),
            method="PUT",
            content_type=content_type,
        )
        return {"type": "gcs", "url": url, "key": key}

    @staticmethod
    def signed_url(path: str, storage: str = "default", expires_in: int = 3600) -> str | None:
        """
        Time-limited read URL for an existing stored object.

        Usage:

            file = session.query(AttachedFile).first()
            url = PresignedUpload.signed_url(file.path, file.storage)
        """

        container = StorageManager._storages.get(storage)
        if container is None:
            return None

        driver_cls = type(container.driver).__name__

        if "S3" in driver_cls or "MinIO" in driver_cls:
            try:
                import boto3

                file_id = path.split("/", 1)[-1]
                return boto3.client("s3").generate_presigned_url(
                    "get_object",
                    Params={"Bucket": container.name, "Key": file_id},
                    ExpiresIn=expires_in,
                )
            except Exception as exc:
                log.warning("S3 signed URL failed for %s: %s", path, exc)
                return None

        if "Google" in driver_cls:
            try:
                from datetime import timedelta

                from google.cloud import storage as gcs  # type: ignore

                file_id = path.split("/", 1)[-1]
                return (
                    gcs.Client()
                    .bucket(container.name)
                    .blob(file_id)
                    .generate_signed_url(
                        version="v4",
                        expiration=timedelta(seconds=expires_in),
                        method="GET",
                    )
                )
            except Exception as exc:
                log.warning("GCS signed URL failed for %s: %s", path, exc)
                return None

        return None

    @staticmethod
    def confirm(key: str, storage: str = "default") -> AttachedFile:
        """
        Build an AttachedFile from a key already uploaded via presigned URL.
        Assign to the model column and commit.


        Usage:

            file = PresignedUpload.confirm(key=req.key, storage=req.storage)
            user.avatar = file
            session.add(user); session.commit()
        """

        container = StorageManager._storages.get(storage)
        if container is None:
            raise ValueError(f"Storage '{storage}' is not configured.")
        try:
            obj = container.get_object(object_name=key)
        except Exception as exc:
            raise FileNotFoundError(f"Object '{key}' not found in '{storage}': {exc}") from exc

        return AttachedFile(
            {
                "file_id": obj.name,
                "filename": key.split("/")[-1],
                "content_type": getattr(obj, "extra", {}).get("content_type", "application/octet-stream"),
                "upload_storage": storage,
                "path": f"{storage}/{obj.name}",
                "url": obj.get_cdn_url(),
                "saved": True,
            }
        )
