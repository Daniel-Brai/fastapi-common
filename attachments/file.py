import mimetypes
from typing import Any

from sqlalchemy_file import File
from sqlalchemy_file.mutable_list import MutableList
from sqlalchemy_file.storage import StorageManager


class AttachedFile(File):
    """
    Subclass of sqlalchemy-file's `File` that adds typed property access,
    type guards, thumbnail support, streaming, async purge, and presigned URLs.

    Usage:

        class User(SQLModel, table=True):
            avatar: AttachedFile | None = blob_field(image=True)

        user.avatar.url
        user.avatar.filename
        user.avatar.size
        user.avatar.extension          # "jpeg"
        user.avatar.is_image           # True
        user.avatar.width              # 1920 (set by ImageValidator)
        user.avatar.thumbnail_url      # set by ThumbnailGenerator
        user.avatar.read()             # bytes
        user.avatar.stream()           # iterator
        user.avatar.presigned_url()    # time-limited S3/GCS URL
        user.avatar.to_dict()          # clean dict for API responses
        user.avatar.purge()            # async storage deletion
    """

    @property
    def url(self) -> str | None:
        try:
            return self.get_cdn_url()
        except Exception:
            return self.get("url")

    @property
    def filename(self) -> str | None:
        return self.get("filename")

    @property
    def content_type(self) -> str | None:
        return self.get("content_type")

    @property
    def mime_type(self) -> str | None:
        return self.get("content_type")

    @property
    def file_id(self) -> str | None:
        return self.get("file_id")

    @property
    def upload_storage(self) -> str | None:
        return self.get("upload_storage")

    @property
    def uploaded_at(self) -> str | None:
        return self.get("uploaded_at")

    @property
    def saved(self) -> bool:
        return bool(self.get("saved", False))

    @property
    def size(self) -> int | float | None:
        """
        File size in bytes. Set by sqlalchemy-file on upload.
        """

        return self.get("size")

    @property
    def path(self) -> str | None:
        """
        {upload_storage}/{file_id} key for StorageManager.get_file().
        """

        s, f = self.upload_storage, self.file_id
        return f"{s}/{f}" if s and f else None

    @property
    def extension(self) -> str | None:
        """
        File extension derived from content_type first, filename as fallback.
        Returns "jpeg" not ".jpeg".
        """

        if ct := self.content_type:
            ext = mimetypes.guess_extension(ct)
            if ext:
                return ext.lstrip(".")

        if fn := self.filename:
            return fn.rsplit(".", 1)[-1] if "." in fn else None

        return None

    @property
    def is_image(self) -> bool:
        return (self.content_type or "").startswith("image/")

    @property
    def is_video(self) -> bool:
        return (self.content_type or "").startswith("video/")

    @property
    def is_pdf(self) -> bool:
        return self.content_type == "application/pdf"

    @property
    def is_audio(self) -> bool:
        return (self.content_type or "").startswith("audio/")

    @property
    def width(self) -> int | float | None:
        return self.get("width")

    @property
    def height(self) -> int | float | None:
        return self.get("height")

    @property
    def thumbnail(self) -> dict[str, Any] | None:
        """
        Thumbnail metadata written by ThumbnailGenerator.

        Keys: url, path, width, height, file_id, upload_storage.
        """
        return self.get("thumbnail")

    @property
    def thumbnail_url(self) -> str | None:
        t = self.thumbnail
        return t.get("url") if t else None

    def read(self) -> bytes:
        """
        Read the full file from storage and return raw bytes.

        Usage:

            pdf_bytes = user.contract.read()
        """

        if not self.path:
            raise ValueError("File has no storage path.")

        return StorageManager.get_file(self.path).read()

    def stream(self):
        """
        Return a libcloud streaming iterator over the file bytes.

        Useful for large files or when the storage provider supports streaming.

        Usage:

            return StreamingResponse(user.video.stream(), media_type="video/mp4")
        """

        if not self.path:
            raise ValueError("File has no storage path.")

        return StorageManager.get_file(self.path).object.as_stream()

    def presigned_url(self, expires_in: int = 3600) -> str | None:
        """
        Generate a time-limited signed read URL (S3 / GCS).
        Returns None for local storage or on failure.

            url = user.contract.presigned_url(expires_in=300)
        """

        from attachments.upload import PresignedUpload

        if not self.path:
            return None
        try:
            return PresignedUpload.signed_url(
                self.path,
                storage=self.upload_storage or "default",
                expires_in=expires_in,
            )
        except Exception:
            return self.url

    def purge(self) -> None:
        """
        Enqueue async deletion of this file and its thumbnail (if any).

        Caller must also set the column to None and commit.

        Usage:

            user.avatar.purge()
            user.avatar = None
            session.add(user)
            session.commit()
        """

        from lib.attachments.jobs import PurgeAttachmentJob

        if self.path:
            PurgeAttachmentJob.perform_later(self.path)

        if t := self.thumbnail:
            if p := t.get("path"):
                PurgeAttachmentJob.perform_later(p)

    def to_dict(self) -> dict:
        """
        Retrieve a dictionary for this file metadata

        Usage:

            class UserResponse(BaseModel):
                avatar: AttachmentSchema | None

            return UserResponse(avatar=AttachmentSchema.from_attached_file(user.avatar))
        """

        return {
            k: v
            for k, v in {
                "file_id": self.file_id,
                "filename": self.filename,
                "content_type": self.content_type,
                "size": self.size,
                "url": self.url,
                "path": self.path,
                "upload_storage": self.upload_storage,
                "uploaded_at": self.uploaded_at,
                "width": self.width,
                "height": self.height,
                "thumbnail": self.thumbnail,
            }.items()
            if v is not None
        }

    def __repr__(self) -> str:
        return f"<AttachedFile {self.filename!r} ({self.content_type})>"


class AttachedFiles(MutableList[File]):
    """
    A custom type for the list of `AttachedFile` objects returned by `AttachedFilesField` columns.

    Usage:

        class User(SQLModel, table=True):
            documents: AttachedFiles = blob_field(image=False, multiple=True)

        user.documents.urls
        user.documents.filenames
        user.documents[0].presigned_url()
        user.documents.attach(open("report.pdf", "rb"))
        user.documents.purge()
        user.documents.purge_at(0)
        user.documents.purge_with("documents_storage/abc-123")
    """

    def __init__(self, files: File | list[File] | MutableList[File]):
        if isinstance(files, File):
            files = [files]

        super().__init__(
            (AttachedFile(f) if not isinstance(f, AttachedFile) and f is not None and isinstance(f, File) else f)
            for f in files
        )

    @property
    def attached(self) -> bool:
        return len(self) > 0

    @property
    def urls(self) -> list[str]:
        return [f.url for f in self if f.url]

    @property
    def filenames(self) -> list[str]:
        return [f.filename for f in self if f.filename]

    @classmethod
    def __class_getitem__(cls, index):
        return super().__class_getitem__(index)

    def attach(self, *files) -> None:
        """
        Append one or more files to the list.
        Accepts the same inputs as FileField: str, bytes, file-like, or File.
        sqlalchemy-file processes each on the next session flush/commit.
        Caller must save the record to persist the column change.

        Usage:

            user.documents.attach(open("report.pdf", "rb"), open("invoice.pdf", "rb"))
            session.add(user)
            session.commit()
        """

        self.extend(files)

    def purge(self) -> None:
        """
        Async-delete every file in the list and clear it.

        Caller must save the record to persist the column change.

        Usage:

            user.documents.purge()
            session.add(user)
            session.commit()
        """

        for f in self:
            f.purge()

        self.clear()

    def purge_at(self, index: int) -> None:
        """
        Async-delete the file at `index` and remove it from the list.

        Caller must save the record to persist the column change.

        Usage:

            user.documents.purge_at(0)
            session.add(user)
            session.commit()
        """

        if index < 0 or index >= len(self):
            raise IndexError(f"Index {index} out of range (count={len(self)})")

        self[index].purge()
        del self[index]

    def purge_with(self, path: str) -> None:
        """
        Async-delete the file whose path matches `path` and remove it from the list.

        Caller must save the record to persist the column change.

        Usage:

            user.documents.purge_with("documents_storage/abc-123-uuid")
            session.add(user)
            session.commit()
        """

        for i, f in enumerate(self):
            if f.path == path:
                f.purge()
                del self[i]
                return

        raise ValueError(f"No attached file found with path '{path}'.")

    def __repr__(self) -> str:
        return f"<AttachedFiles count={len(self)}>"
