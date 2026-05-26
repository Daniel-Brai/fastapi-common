class MailerError(Exception):
    """
    Base for all mailer errors
    """

    def __init__(self, message: str = "An email delivery error occurred"):
        self.type = "mailer_error"
        self.message = message
        super().__init__(message)


class MailerConnectionError(MailerError):
    def __init__(self, message: str = "Could not connect to the mail server"):
        super().__init__(message)


class MailerAuthError(MailerError):
    def __init__(self, message: str = "Mail server authentication failed"):
        super().__init__(message)


class MailerInvalidRecipientError(MailerError):
    def __init__(self, message: str = "One or more recipient addresses were rejected"):
        super().__init__(message)


class MailerTemplateError(MailerError):
    def __init__(self, message: str = "Failed to render email template"):
        super().__init__(message)


class MailerNotConfiguredError(RuntimeError):
    def __init__(self, message: str = "Mailer is not configured properly. Call configure_mailer() at startup."):
        super().__init__(message)


class MailerTransportNotConfiguredError(MailerError):
    def __init__(self, message: str = "No transport configured for the mailer"):
        super().__init__(message)


class MailerTemplateAssetError(MailerError):
    def __init__(self, message: str = "Failed to load an asset for a template"):
        super().__init__(message)


class MailerAttachmentFetchError(MailerError):
    """
    Raised when a URL attachment cannot be fetched (network error or non-2xx).
    """

    def __init__(self, message: str = "Failed to fetch attachment from URL"):
        super().__init__(message)


class MailerAttachmentReadError(MailerError):
    """
    Raised when a local path attachment cannot be read
    """

    def __init__(self, message: str = "Failed to read attachment from disk"):
        super().__init__(message)
