from typing import Any, ClassVar, cast

import inflection
from pydantic import BaseModel, ConfigDict

from lib.forms.constants import FORM_CONFIG_ATTRS
from lib.forms.schemas import FormConfig, FormConfigDict


class BaseForm(BaseModel):
    """
    Base class for all application forms.


    Example:

       class LoginForm(BaseForm):
            form_config = FormConfigDict(
                submit_url="/api/v1/auth/login",
                submit_context=SubmitContext(
                    success=FormSubmissionSuccessContext(
                        name="toast",
                        context={"message": "Logged in!", "type": "success"},
                        redirect_to="/dashboard",
                        redirect_delay_secs=2,
                    ),
                    error=FormSubmissionErrorContext(
                        name="alert",
                        context={"message": "{error.detail}", "type": "error"},
                    ),
                ),
            )

            email:    EmailStr = FormField("email",    html_attrs={"placeholder": "you@example.com"})
            password: str      = FormField("password", html_attrs={"placeholder": "Password"})

            def to_submit_schema(self) -> LoginSchema:
                return LoginSchema(email=self.email, password=self.password)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    form_config: ClassVar[FormConfigDict] = {}

    @classmethod
    def get_form_name(cls) -> str:
        return inflection.underscore(cls.__name__)

    @classmethod
    def get_form_config(cls) -> FormConfig:
        resolved = FormConfig()

        for klass in cls.__mro__:
            if klass is BaseForm:
                break
            cfg = klass.__dict__.get("form_config")
            if cfg is not None:
                for attr in FORM_CONFIG_ATTRS:
                    if attr in cfg:
                        setattr(resolved, attr, cfg[attr])
                break

        if resolved.target is None:
            resolved.target = f"#{cls.get_form_name()}"

        return resolved

    @classmethod
    def get_field_form_meta(cls, field_name: str) -> dict[str, Any]:
        fi = cls.model_fields.get(field_name)
        if fi is None:
            return {}

        extra = fi.json_schema_extra
        if callable(extra):
            try:
                extra = extra({})
            except Exception:
                return {}

        if not isinstance(extra, dict):
            return {}

        form_meta = extra.get("form")
        return cast(dict[str, Any], form_meta) if isinstance(form_meta, dict) else {}

    @classmethod
    def is_valid(cls) -> bool:
        for field_name in cls.model_fields:
            if not cls.get_field_form_meta(field_name).get("field_type"):
                return False
        return True

    @classmethod
    def get_form_url(cls) -> str:
        """
        Get the renderable URL for this form
        """

        from lib.forms.config import get_form

        return f"{get_form().route_prefix}/{cls.get_form_name()}"

    def to_submit_schema(self) -> Any:
        """
        Override to transform this form instance into the schema your service expects.
        If not overridden, model_dump() is passed directly to the service.

        Example::

            def to_submit_schema(self) -> LoginSchema:
                return LoginSchema(email=self.email, password=self.password)
        """
        return None
