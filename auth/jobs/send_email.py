from typing import Any

from lib.jobs import BaseJob, JobError
from lib.mailer import MailerError


class SendAuthEmailJob(BaseJob):
    """
    Send authentication-related email job

    This job lives on the "mailer" queue so email delivery never blocks an HTTP response.

    All six AuthMailer.send_* methods enqueue via this job instead of calling the mailer transport directly.

    Enqueue from anywhere in the auth lib (or your own code):

        SendAuthMailerJob.perform_later(
            "send_password_reset",
            to    = user.email,
            token = reset_token,
            name  = user.get_display_name(),
        )

    The first positional argument is always the AuthMailer method name.
    All remaining arguments are keyword arguments forwarded to that method.

    Supported method names (mirror AuthMailer public API):
        send_verification_email
        send_password_reset
        send_magic_link
        send_email_change_verification
        send_password_changed_notice
        send_email_changed_notice
        send_account_recovery_email

    Configuration:
        queue: "mailer"
        max_attempts: 3
    """

    queue = "mailer"
    max_attempts = 3
    retry_on = (MailerError,)

    _REQUIRED_KWARGS: dict[str, frozenset[str]] = {
        "send_verification_email": frozenset({"to", "token"}),
        "send_password_reset": frozenset({"to", "token"}),
        "send_magic_link": frozenset({"to", "token"}),
        "send_email_change_verification": frozenset({"to", "token", "new_email"}),
        "send_password_changed_notice": frozenset({"to"}),
        "send_email_changed_notice": frozenset({"to", "old_email"}),
        "send_account_recovery_email": frozenset({"to", "token"}),
    }

    @classmethod
    def perform_later(cls, method: str, **kwargs: Any):
        """
        Enqueue a SendAuthMailerJob.

        Validates the method name and required kwargs at enqueue time so
        errors surface immediately rather than in the worker.

        Parameters
        ----------
        method
            AuthMailer method name (e.g. "send_password_reset").
        **kwargs
            Keyword arguments forwarded to the method.
        """

        if method not in cls._REQUIRED_KWARGS:
            raise JobError(
                f"SendAuthEmailJob: Unknown AuthMailer method {method!r}. "
                f"Valid options: {sorted(cls._REQUIRED_KWARGS)}"
            )

        required = cls._REQUIRED_KWARGS[method]
        missing = required - set(kwargs)

        if missing:
            raise JobError(
                f"SendAuthEmailJob: SendAuthEmailJob.perform_later({method!r}) method missing "
                f"required kwargs: {sorted(missing)}"
            )

        return super().perform_later(method, **kwargs)

    def perform(self, method: str, **kwargs: Any) -> None:
        """
        Execute the queued AuthMailer method inside the worker process.
        """

        try:
            self.logger.info(
                f"SendAuthMailerJob: preparing to send email with method {method!r} to {kwargs.get('to', '?')}"
            )

            from lib.auth.config import get_mailer

            mailer = get_mailer()
            send_fn = getattr(mailer, method, None)

            if send_fn is None:
                self.logger.warning(
                    f"SendAuthMailerJob: AuthMailer has no async method {method!r}. "
                    f"Ensure the method name passed to perform_later is correct."
                )
                return

            self.logger.info(f"SendAuthMailerJob: executing {method}(to={kwargs.get('to', '?')})")

            self.run_async(send_fn(**kwargs))
        except Exception as e:
            self.logger.exception(f"SendAuthMailerJob: failed to send email with exception - {e}")
            raise e
