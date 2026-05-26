class AttachmentError(Exception):
    """
    Base exception for attachment-related errors.
    """

    def __init__(self, message: str = "An error occurred while processing the attachment"):
        self.type = "attachment_error"
        self.message = message
        super().__init__(self.message)

    @staticmethod
    def from_exc(e: Exception) -> "AttachmentError":
        """
        Factory method to create an AttachmentError from a generic exception.
        """
        return AttachmentError(str(e))
