from typing import Any, Awaitable, Callable, Literal, NotRequired, TypedDict

type HTMXSwap = Literal[
    "innerHTML",
    "outerHTML",
    "beforebegin",
    "afterbegin",
    "beforeend",
    "afterend",
    "delete",
    "none",
]

type HTMXTrigger = Literal[
    "click",
    "change",
    "submit",
    "load",
    "revealed",
    "intersect",
] | str


class Button(TypedDict):
    """
    Schema representing a form button

    Attributes:
        text_or_html (str): The text or html inside the button
        html_attrs (dict[str, Any]): The HTML attributes on the button e.g class, id, type and so on
    """

    text_or_html: str
    html_attrs: dict[str, Any]


class BaseFormSubmissionContext(TypedDict):
    """
    Schema representing the context of a form submission, this is the context passed to the form on what to do when the form is submitted
    """

    name: Literal["alert", "modal", "toast", "no-op"]
    context: dict[str, Any] | None


class FormSubmissionSuccessContext(BaseFormSubmissionContext):
    """
    Describes what happens on a successful submission (HTTP 200 - 399).

    name:
        The JS component name: "toast" | "alert" | "modal" | "no-op" (client handles via form.js).

    context:
        The context dict passed to the JS component.

    redirect_to:
        Client-side redirect URL.  Only honoured if the server response does
        NOT include HX-Redirect or HX-Location headers.

    redirect_delay_secs:
        Seconds before the redirect fires.  Omit or set to 0 for immediate.

    condition:
        Optional JavaScript expression evaluated against the response payload.
        If falsy, the current context is skipped and the optional fallback is used.

    fallback:
        Optional alternate success context to use when ``condition`` evaluates
        to false.
    """

    redirect_to: NotRequired[str | None]
    redirect_delay_secs: NotRequired[int | None]
    condition: NotRequired[str]
    fallback: NotRequired[BaseFormSubmissionContext]


class FormSubmissionErrorContext(BaseFormSubmissionContext):
    """
    Describes what happens on a failed submission (HTTP 400 - 599).

    name:
        The JS component name: "toast" | "alert" | "modal" | "no-op" (client handles via form.js).

    context:
        The context dict passed to the JS component.
    """

    pass


class SubmitContext(TypedDict, total=False):
    """
    Schema representing the context of a form submission.

    This is the context passed to the form on what to do when the form is submitted

    Examples::

        submit_context = SubmitContext(
            success=FormSubmissionSuccessContext(
                name="toast",
                context={"message": "Logged in!", "type": "success", "position": "top-right"},
                redirect_to="/dashboard",
                redirect_delay_secs=2,
            ),
            error=FormSubmissionErrorContext(
                name="alert",
                context={"message": "{error.detail}", "type": "error"},
            ),
        )
    """

    success: FormSubmissionSuccessContext | None
    error: FormSubmissionErrorContext | None


ConfigKeys = Literal[
    "target",
    "trigger",
    "swap",
    "inline_validation",
    "inline_validation_threshold_seconds",
    "with_credentials",
    "submit_on_page_load",
    "submit_service",
    "submit_url",
    "submit_method",
    "encoding",
    "submit_context",
    "buttons",
]

AttributesIfKey = (
    ConfigKeys
    | Literal[
        "target:not",
        "trigger:not",
        "swap:not",
        "inline_validation:not",
        "inline_validation_threshold_seconds:not",
        "with_credentials:not",
        "submit_on_page_load:not",
        "submit_service:not",
        "submit_url:not",
        "submit_method:not",
        "encoding:not",
        "submit_context:not",
        "buttons:not",
    ]
)

type ConditionType = (bool | Callable[[], bool] | Callable[[], Awaitable[bool]] | Awaitable[bool])

type AttributesIf = dict[AttributesIfKey, tuple[ConditionType, Any]]
