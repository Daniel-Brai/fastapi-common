from lib.database.mixins.created_datetime import CreatedDateTimeMixin
from lib.database.mixins.updated_datetime import UpdatedDateTimeMixin


class TimestampMixin(CreatedDateTimeMixin, UpdatedDateTimeMixin):
    """
    Mixin that adds created and updated datetime columns to a model

    Attributes:
        created_at (datetime): The datetime when the record was created.
        updated_at (datetime | None): The datetime when the record was last updated.
    """

    pass
