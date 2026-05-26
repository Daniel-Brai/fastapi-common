from fastapi import FastAPI

from lib.forms.exceptions import FormConfigError
from lib.forms.form import Form
from lib.templates import TemplateEngine


class FormRegistry:
    """
    Registry for the configured Form instance.
    """

    def __init__(self) -> None:
        self.form: Form | None = None

    def configure_forms(
        self,
        app: FastAPI,
        template_engine: TemplateEngine,
        components: dict[str, str],
        modules: list[str],
        route_prefix: str = "/forms",
        use_i18n: bool = False,
    ) -> "FormRegistry":
        """
        Instantiate and store the Form class.
        """
        self.form = Form(
            app=app,
            template_engine=template_engine,
            components=components,
            modules=modules,
            route_prefix=route_prefix,
            use_i18n=use_i18n,
        )
        return self

    def get_form(self) -> "Form":
        if self.form is None:
            raise FormConfigError()

        return self.form


form_registry = FormRegistry()
