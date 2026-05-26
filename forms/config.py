from fastapi import FastAPI

from lib.forms.registry import form_registry
from lib.templates.types import TemplateEngine


def configure_forms(
    app: FastAPI,
    template_engine: TemplateEngine,
    components: dict[str, str],
    modules: list[str],
    route_prefix: str = "/forms",
    use_i18n: bool = False,
):
    """
    Configure and store the Form instance. Accepts same arguments as Form.__init__.
    """
    return form_registry.configure_forms(
        app=app,
        template_engine=template_engine,
        components=components,
        modules=modules,
        route_prefix=route_prefix,
        use_i18n=use_i18n,
    )


def get_form():
    """
    Return the configured Form instance, or raise if not configured.
    """
    return form_registry.get_form()
