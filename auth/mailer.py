from lib.logger import get_logger

logger = get_logger("lib.auth.mailer")


class AuthMailer:
    """
    Auth-related emails sender.

    It requires your mailer to be configured using :meth:`~lib.mailer.configure_mailer` first from the `lib.mailer` library and provides methods to send emails for various auth-related actions, such as:

    - Email verification
    - Password reset
    - Magic link sign-in
    - Email change verification
    - Password change notification
    - Email change notification

    Parameters
    ----------
    base_url
        Root URL of your frontend app.  Used to build token links, e.g.:
        https://yourapp.com/auth/reset-password?token=...

    templates
        Optional mapping of logical name and template file name.

        Defaults:

            password_reset       - `email_password_reset.mjml.html`
            verify_email         - `email_verify_email.mjml.html`
            magic_link           - `email_magic_link.mjml.html`
            change_email         - `email_change_email.mjml.html`
            password_changed     - `email_password_changed.mjml.html`
            email_changed        - `email_email_changed.mjml.html`
            account_recovery     - `email_account_recovery.mjml.html`
    """

    _DEFAULT_TEMPLATES = {
        "password_reset": "email_password_reset.mjml.html",
        "verify_email": "email_verify_email.mjml.html",
        "magic_link": "email_magic_link.mjml.html",
        "change_email": "email_change_email.mjml.html",
        "password_changed": "email_password_changed.mjml.html",
        "email_changed": "email_email_changed.mjml.html",
        "email_account_recovery": "email_account_recovery.mjml.html",
    }

    def __init__(
        self,
        base_url: str,
        templates: dict[str, str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._templates = {**self._DEFAULT_TEMPLATES, **(templates or {})}

    def _t(self, key: str) -> str:
        return self._templates[key]

    @property
    def _mailer(self):
        from lib.mailer import get_mailer

        return get_mailer()

    async def send_verification_email(self, *, to: str, token: str, name: str | None = None) -> None:
        """
        Template context:
            name            str | None
            email           str
            verification_url str   — {base_url}/auth/verify-email/{token}
        """
        await self._mailer.send_template(
            to=to,
            subject="Verify your email address",
            template=self._t("verify_email"),
            context={
                "name": name,
                "email": to,
                "verification_url": f"{self._base_url}/auth/verify-email/{token}",
            },
        )

    async def send_password_reset(self, *, to: str, token: str, name: str | None = None) -> None:
        """
        Template context:
            name            str | None
            email           str
            reset_url       str   — {base_url}/auth/reset-password?token={token}
        """
        await self._mailer.send_template(
            to=to,
            subject="Reset your password",
            template=self._t("password_reset"),
            context={
                "name": name,
                "email": to,
                "reset_url": f"{self._base_url}/auth/reset-password?token={token}",
            },
        )

    async def send_magic_link(self, *, to: str, token: str, name: str | None = None) -> None:
        """
        Template context:
            name        str | None
            email       str
            magic_url   str   — {base_url}/auth/magic-link/{token}
        """
        await self._mailer.send_template(
            to=to,
            subject="Your sign-in link",
            template=self._t("magic_link"),
            context={
                "name": name,
                "email": to,
                "magic_url": f"{self._base_url}/auth/magic-link/{token}",
            },
        )

    async def send_email_change_verification(
        self, *, to: str, token: str, new_email: str, name: str | None = None
    ) -> None:
        """
        Template context:
            name            str | None
            email           str   — the NEW address (where the email is sent)
            new_email       str
            confirm_url     str   — {base_url}/auth/verify-email-change/{token}
        """
        await self._mailer.send_template(
            to=to,
            subject="Confirm your new email address",
            template=self._t("change_email"),
            context={
                "name": name,
                "email": to,
                "new_email": new_email,
                "confirm_url": f"{self._base_url}/auth/verify-email-change/{token}",
            },
        )

    async def send_password_changed_notice(self, *, to: str, name: str | None = None) -> None:
        """
        Template context:
            name            str | None
            email           str
            reset_url       str   ({base_url}/auth/forgot-password)
        """

        await self._mailer.send_template(
            to=to,
            subject="Your password was changed",
            template=self._t("password_changed"),
            context={
                "name": name,
                "email": to,
                "reset_url": f"{self._base_url}/auth/forgot-password",
            },
        )

    async def send_email_changed_notice(self, *, to: str, old_email: str, name: str | None = None) -> None:
        """
        Sent to the *old* address after an email change is confirmed.

        Examples:

            Template context:
                name        str | None
                email       str  (the old address)
                old_email   str
        """
        await self._mailer.send_template(
            to=to,
            subject="Your email address was changed",
            template=self._t("email_changed"),
            context={
                "name": name,
                "email": to,
                "old_email": old_email,
            },
        )

    async def send_account_recovery_email(self, *, to: str, token: str, name: str | None = None) -> None:
        await self._mailer.send_template(
            to=to,
            subject="Account Recovery",
            template=self._t("email_account_recovery"),
            context={
                "name": name,
                "email": to,
                "recovery_url": f"{self._base_url}/auth/verify-account-recovery/{token}",
            },
        )
