from typing import Any, List

from sqlalchemy import Column
from sqlalchemy_file.processors import Processor
from sqlalchemy_file.validators import Validator
from sqlmodel import Field

from lib.attachments.types import AttachedFileField, AttachedFilesField, AttachedImageField


def blob_field(
    *,
    nullable: bool = True,
    image: bool = False,
    validators: List[Validator] | None = None,
    processors: List[Processor] | None = None,
    upload_storage: str | None = None,
    extra: dict | None = None,
    headers: dict | None = None,
    **field_kwargs,
) -> Any:
    """
    Single-file storage column.

    Examples:

        ##### Basic
        avatar_blob: File | None = blob_field(image=True)

        ##### With validators and processors
        cover_blob: File | None = blob_field(
            image=True,
            validators=[SizeValidator("2m"), ContentTypeValidator(["image/jpeg", "image/png"])],
            processors=[ThumbnailGenerator(thumbnail_size=(128, 128))],
        )

        ### Private S3 object
        contract_blob: str | None = blob_field(
            upload_storage="s3_private",
            extra={"acl": "private"},
            headers={"Cache-Control": "no-store"},
        )
    """

    kwargs: dict = {}
    if validators:
        kwargs["validators"] = validators
    if processors:
        kwargs["processors"] = processors
    if upload_storage:
        kwargs["upload_storage"] = upload_storage
    if extra:
        kwargs["extra"] = extra
    if headers:
        kwargs["headers"] = headers

    col = AttachedImageField(**kwargs) if image else AttachedFileField(**kwargs)

    if nullable:
        return Field(sa_column=Column(col, nullable=True, default=None), **field_kwargs)

    return Field(sa_column=Column(col, nullable=False), **field_kwargs)


def blobs_field(
    *,
    nullable: bool = True,
    validators: List[Validator] | None = None,
    processors: List[Processor] | None = None,
    upload_storage: str | None = None,
    extra: dict | None = None,
    headers: dict | None = None,
    **field_kwargs,
) -> Any:
    """
    Multi-file storage column

    sqlalchemy-file stores each file individually and returns a list of File
    objects. Validators and processors are applied to
    every file in the list on save.

    Examples:

        ##### Basic
        documents_blobs: list[File] | None = blobs_field()

        ####### With validators:
        assets_blobs: list[File] | None = blobs_field(
            validators=[
                SizeValidator("10m"),
                ContentTypeValidator(["application/pdf", "image/png"]),
            ],
        )

        #####On a specific storage:
        media_blobs: list[File] | None = blobs_field(upload_storage="cdn_storage")
    """

    kwargs: dict[str, Any] = {"multiple": True}
    if validators:
        kwargs["validators"] = validators
    if processors:
        kwargs["processors"] = processors
    if upload_storage:
        kwargs["upload_storage"] = upload_storage
    if extra:
        kwargs["extra"] = extra
    if headers:
        kwargs["headers"] = headers

    col = AttachedFilesField(**kwargs)

    if nullable:
        return Field(sa_column=Column(col, nullable=True, default=None), **field_kwargs)

    return Field(sa_column=Column(col, nullable=False), **field_kwargs)
