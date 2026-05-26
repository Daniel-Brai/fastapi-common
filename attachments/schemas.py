from typing import Any, Self

from pydantic import BaseModel, Field

from lib.attachments.file import AttachedFiles


class ThumbnailSchema(BaseModel):
    """
    Schema for a thumbnail of an attachment.

    Attributes:
        url (str | None): The URL to access the thumbnail.
        path (str | None): The storage path of the thumbnail.
        width (int | None): The width of the thumbnail.
        height (int | None): The height of the thumbnail.
        file_id (str | None): The unique identifier of the thumbnail file.
        upload_storage (str | None): The name of the storage where the thumbnail file is uploaded.
    """

    url: str | None = None
    path: str | None = None
    width: int | None = None
    height: int | None = None
    file_id: str | None = None
    upload_storage: str | None = None


class AttachmentSchema(BaseModel):
    """
    Schema for an attachment.

    Attributes:
        file_id (str | None): The unique identifier of the file.
        filename (str | None): The original name of the uploaded file.
        content_type (str | None): The content type of the uploaded file.
        size (int | None): The size of the file in bytes.
        url (str | None): The URL to access the file.
        path (str | None): The storage path of the file.
        upload_storage (str | None): The name of the storage where the file is uploaded.
        uploaded_at (str | None): The timestamp when the file was uploaded.
        width (int | None): The width of the file (if it's an image).
        height (int | None): The height of the file (if it's an image).
        thumbnail (ThumbnailSchema | None): The thumbnail information of the file (if it's an image).
    """

    file_id: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None
    url: str | None = None
    path: str | None = None
    upload_storage: str | None = None
    uploaded_at: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail: ThumbnailSchema | None = None

    @classmethod
    def from_attached_file(cls, file: Any | None) -> Self | None:
        """
        Create an AttachmentSchema instance from an AttachedFile object, or return None if the file is None.
        """

        if file is None:
            return None

        d = file.to_dict()

        if t := d.get("thumbnail"):
            d["thumbnail"] = ThumbnailSchema(**t)

        return cls(**d)


class AttachmentsSchema(BaseModel):
    """
    Schema for a list of attachments.

    Attributes:
        files (list[AttachmentSchema]): A list of attachment schemas.
    """

    files: list[AttachmentSchema] = Field(default_factory=list, description="A list of attachment schemas.")

    @classmethod
    def from_attached_files(cls, files: AttachedFiles | None) -> Self:
        """
        Create an AttachmentsSchema instance from a list of AttachedFile objects.
        """

        if not files:
            return cls(files=[])

        return cls(files=[s for f in files if (s := AttachmentSchema.from_attached_file(f)) is not None])


class AttachmentPresignItem(BaseModel):
    """
    Schema for an item in the presign upload request.

    Attributes:
        filename (str): The original name of the uploaded file.
        content_type (str): The content type of the uploaded file.
        storage (str, optional): The name of the storage to upload the file to. Defaults
            to "default".
        expires_in (int, optional): The expiration time for the presigned URL in seconds.
            Defaults to 3600 (1 hour).
    """

    filename: str
    content_type: str
    storage: str = "default"
    expires_in: int = 3600


class AttachmentConfirmItem(BaseModel):
    """
    Schema for an item in the confirm upload request.

    Attributes:
        key (str): The key of the uploaded file.
        storage (str, optional): The name of the storage to upload the file to. Defaults
            to "default".
    """

    key: str
    storage: str = "default"


class AttachmentPresignRequest(BaseModel):
    """
    Schema for the presign upload request.

    Attributes:
        files (list[AttachmentPresignItem]): A list of items to presign for upload.
    """

    files: list[AttachmentPresignItem]


class AttachmentConfirmRequest(BaseModel):
    """
    Schema for the confirm upload request.

    Attributes:
        files (list[AttachmentConfirmItem]): A list of items to confirm for upload.
    """

    files: list[AttachmentConfirmItem]
