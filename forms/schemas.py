from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from lib.forms.types import AttributesIf, Button, HTMXSwap, HTMXTrigger, SubmitContext


@dataclass
class FormButtons:
    """
    Schema representing the buttons on a form

    Attributes:
        buttons_container_html_attrs (dict[str, Any] | None): The HTML attributes for the buttons container
        buttons (list[Button]): The buttons to be rendered
    """

    buttons_container_html_attrs: dict[str, Any] | None = None
    buttons: list[Button] = field(default_factory=list)


class FormConfigDict(TypedDict, total=False):
    """
    Declare as a class variable on any BaseForm subclass.

    Examples::

        class LoginForm(BaseForm):
            form_config = FormConfigDict(
                submit_service="app.services.auth.AuthService.login",
                encoding="application/json",
                submit_context=SubmitContext(
                    success=FormSubmissionSuccessContext(
                        name="toast",
                        context={"message": "Welcome back!", "type": "success"},
                        redirect_to="/dashboard",
                        redirect_delay_secs=1,
                    ),
                    error=FormSubmissionErrorContext(
                        name="alert",
                        context={"message": "{error.detail}", "type": "error"},
                    ),
                ),
            )
    """

    target: str
    trigger: HTMXTrigger
    swap: HTMXSwap
    inline_validation: bool
    inline_validation_threshold_seconds: int
    with_credentials: bool
    submit_on_page_load: bool
    submit_service: str
    submit_url: str
    submit_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    encoding: Literal["multipart/form-data", "application/json"]
    use_htmx: bool
    submit_context: SubmitContext | None
    buttons: FormButtons
    attributes_if: AttributesIf
    cancel_target: str | None
    cancel_restore_html: str | None
    css: str | None


@dataclass
class FormConfig:
    """
    Schema for the resolved form configuration, after applying any conditional overrides from ``attributes_if``.

    This is the schema used internally by the form rendering and submission logic.

    Attributes:
        target (str | None): HTMX ``hx-target`` for the form; defaults to ``"#<form_name>"``.
        swap (HTMXSwap): HTMX ``hx-swap`` strategy (default ``"innerHTML"``).
        trigger (HTMXTrigger): HTMX trigger for form submission (default ``"submit"``).
        inline_validation (bool): Enable per-field inline validation via HTMX (default ``False``).
        inline_validation_threshold_seconds (float): Debounce delay in *seconds* before firing inline validation (default ``1.5``). Converted to milliseconds for HTMX.
        submit_service (str | None): Dotted path to a service method that will handle form submissions. If provided, a route will be generated at ``/forms/<form_name>/submit``.
        submit_url (str | None): A raw URL to which the form will be submitted. If provided, no route will be generated and the form will post to this URL instead.
        submit_method (Literal["GET", "POST", "PUT", "PATCH", "DELETE"]): HTTP method to use
        encoding (Literal["multipart/form-data","application/json"]): Form encoding type (default ``"multipart/form-data"``).
        submit_context (SubmitContext | None): Context dict passed to the client to determine what to do on successful or failed submission.
        buttons (FormButtons): The buttons to be rendered on the form, along with any container attributes.
        attributes_if (AttributesIf): A dict of conditional overrides for form configuration values, keyed by dotted path to the config value (e.g. "swap", etc).
                                    The value is a list of condition/context pairs, where the condition is a dotted path to a boolean value in the template context,
                                    and the context is the override value to use if the condition is truthy.
        cancel_target (str | None): If provided, renders a cancel button that targets this HTMX selector.
        cancel_restore_html (str | None): If provided, the HTML to restore in the target
        css (str | None): CSS class string applied to the rendered form element.
    """

    target: str | None = None
    swap: HTMXSwap = "innerHTML"
    trigger: HTMXTrigger = "submit"
    inline_validation: bool = False
    inline_validation_threshold_seconds: float = 1.5
    with_credentials: bool = False
    submit_on_page_load: bool = False
    submit_service: str | None = None
    submit_url: str | None = None
    submit_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    encoding: Literal["multipart/form-data", "application/json"] = "multipart/form-data"
    use_htmx: bool = True
    submit_context: SubmitContext | None = None
    buttons: FormButtons = field(default_factory=FormButtons)
    attributes_if: AttributesIf = field(default_factory=dict)
    cancel_target: str | None = None
    cancel_restore_html: str | None = None
    css: str | None = None
