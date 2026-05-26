from sqlalchemy_file import FileField, ImageField

from lib.attachments.file import AttachedFile, AttachedFiles


class AttachedFileField(FileField):
    """
    A SQLAlchemy column type for storing a single file attachment
    """

    cache_ok = True

    def process_result_value(self, value, dialect):
        result = super().process_result_value(value, dialect)
        return AttachedFile(result) if result is not None else None


class AttachedImageField(ImageField):
    """
    A SQLAlchemy column type for storing a single image attachment
    """

    cache_ok = True

    def process_result_value(self, value, dialect):
        result = super().process_result_value(value, dialect)
        return AttachedFile(result) if result is not None else None


class AttachedFilesField(FileField):
    """
    A SQLAlchemy column type for storing multiple file attachments.
    """

    cache_ok = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def process_result_value(self, value, dialect):
        result = super().process_result_value(value, dialect)
        return AttachedFiles(result) if result is not None else None
