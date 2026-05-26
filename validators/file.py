from pathlib import Path
from typing import TypedDict

from fastapi import UploadFile


class FileValidationResult(TypedDict):
    """
    Schema for the result of validating an uploaded file.
    """

    success: bool
    errors: list[str] | None


def validate_file(
    file: UploadFile | None,
    max_size: int | None = None,
    allowed_content_types: list[str] | None = None,
    allowed_extensions: list[str] | None = None,
    allow_empty: bool = False,
) -> FileValidationResult:
    """
    Validate an uploaded file against size, content type, extension, and empty constraints.

    Args:
        file (UploadFile | None): The file to validate from FastAPI.
        max_size (int | None): Maximum allowed size in bytes.
        allowed_content_types (list[str] | None): List of allowed MIME types.
        allowed_extensions (list[str] | None): List of allowed file extensions (e.g., [".opml", ".xml"]).
        allow_empty (bool): Whether to allow 0 byte files. Default is False.

    Returns:
        FileValidationResult: A dictionary containing the success status and any errors.
    """

    errors: list[str] = []

    if file is None:
        return {"success": False, "errors": ["No file provided"]}

    size = file.size if file.size is not None else 0

    if not allow_empty and size == 0:
        errors.append("File is empty")

    if max_size is not None and size > max_size:
        errors.append(f"File size exceeds maximum allowed size of {max_size} bytes")

    if allowed_content_types and file.content_type not in allowed_content_types:
        errors.append(f"Content type '{file.content_type}' is not allowed")

    if allowed_extensions:
        file_extension = Path(file.filename or "").suffix
        if not any(file_extension.lower().endswith(ext.lower()) for ext in allowed_extensions):
            errors.append(f"File extension must be one of: {', '.join(allowed_extensions)}")

    if errors:
        return {"success": False, "errors": errors}

    return {"success": True, "errors": None}
