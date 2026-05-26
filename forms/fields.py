from typing import Any

from pydantic import Field

from lib.forms.types import ConfigKeys


def FormField(
    field_type: str,
    html_attrs: dict[str, Any] | None = None,
    config_overrides: dict[ConfigKeys | str, Any] | None = None,
    **pydantic_kwargs: Any,
) -> Any:
    """
    Declare a typed form field on a :class:`~forms.base.BaseForm` subclass.

    Args:
        field_type: str
            The template key that maps this field to a component template, e.g.
            ``"text"``, ``"email"``, ``"select"``.  The key must exist in the
            ``components`` dict supplied to :class:`~forms.form.Form`.

        html_attrs: dict[str, Any]
            A free-form dict whose contents are forwarded verbatim as template
            context when the field is rendered.  Typical keys:

            * ``title``       : human-readable label (defaults to the field name
                                if absent).
            * ``placeholder`` : input placeholder text.
            * ``class``       : extra CSS classes for the input element.
            * ``id``          : explicit HTML id (auto-derived otherwise).
            * Any valid HTML attribute string.

        config_overrides: dict[ConfigKeys, Any]
            A dict of optional overrides for the field's behavior that would otherwise be determined by the form's configuration.  For example, if the form has ``inline_validation`` enabled, you can disable it for a specific field by setting ``config_overrides={"inline_validation": False}``.

        **pydantic_kwargs:
            Forwarded directly to :func:`pydantic.Field`.  Useful values include
            ``alias``, ``default``, ``ge``, ``le``, ``gt``, ``lt``,
            ``min_length``, ``max_length``, ``description``, etc.

            ``alias``: if supplied, the HTML ``<input name="…">`` will use the
            alias value rather than the Python field name.  The form submission
            is then expected to send ``alias`` as the key.

    Returns:
        A :class:`pydantic.fields.FieldInfo` with form metadata stored in
        ``json_schema_extra["form"]``.

    Example::

        class LoginForm(BaseForm):
            email: str = FormField(
                "email",
                html_attrs={"label": "Email Address", "placeholder": "you@example.com"},
            )
            password: str = FormField(
                "password",
                html_attrs={"label": "Password", "autocomplete": "current-password"},
                min_length=8,
            )
            # The HTML input will use name="full_name" instead of "display_name"
            display_name: str = FormField(
                "text",
                html_attrs={"label": "Display Name"},
                alias="full_name",
            )
    """

    return Field(
        json_schema_extra={
            "form": {
                "field_type": field_type,
                "html_attrs": html_attrs or {},
                "config_overrides": config_overrides or {},
            }
        },
        **pydantic_kwargs,
    )
