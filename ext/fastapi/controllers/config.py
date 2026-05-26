from typing import Any, Callable

from lib.templates import TemplateEngine

from .core import Controller


def configure_controllers(
    template_engine: TemplateEngine,
    template_render_callback: Callable[[str, float], Any] | None = None,
):
    """
    Configures the controllers with the provided configuration parameters.

    Args:
        template_engine (TemplateEngine): The template engine to be used by the controllers.
        template_render_callback (Callable[[str, float], Any] | None):
            Optional callback executed after every template render.

    Returns:
        None
    """

    Controller.set_template_engine(
        template_engine,
        template_render_callback=template_render_callback,
    )
