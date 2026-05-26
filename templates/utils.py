from pathlib import Path
from typing import Any, Callable

from anyio import Path as AsyncPath
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette_async_jinja import AsyncJinja2Templates

from lib.templates.types import TemplateEngine

type ContextProcessor = Callable[[Request | Any], dict[str, Any]]


def create_template_engine(
    template_dir: Path | AsyncPath,
    async_mode: bool = False,
    context_processors: list[ContextProcessor] | None = None,
    env_globals: dict[str, Any] | None = None,
    env_filters: dict[str, Any] | None = None,
    **env_options: Any,
) -> TemplateEngine:
    """
    Factory function to create a template engine instance based on the specified mode.

    Args:
        template_dir (Path | AsyncPath): The directory where templates are located.
        async_mode (bool): If True, creates an AsyncJinja2Templates instance; otherwise, creates a Jinja2Templates instance.
        context_processors (list[ContextProcessor] | None): Optional list of callables that receive a request and return a dict merged into every template context.
        env_globals (dict[str, Any] | None): Additional globals to add to the Jinja2 environment.
        env_filters (dict[str, Any] | None): Additional filters to add to the Jinja2 environment.
        **env_options: Extra keyword arguments forwarded to the underlying template engine constructor.

    Returns:
        TemplateEngine: An instance of either Jinja2Templates or AsyncJinja2Templates based on the async_mode flag.

    Raises:
        ValueError: If async_mode is True and template_dir is not an :class:`AsyncPath`.
    """

    if async_mode:
        if not isinstance(template_dir, AsyncPath):
            raise ValueError("`template_dir` must be an `AsyncPath` i.e `Path` from `anyio` when async_mode is True")

        engine = AsyncJinja2Templates(
            directory=template_dir,
            context_processors=context_processors,
            enable_async=True,
        )
    else:
        engine = Jinja2Templates(
            directory=template_dir,
            context_processors=context_processors,
            **env_options,
        )

    if env_globals:
        engine.env.globals.update(env_globals)

    if env_filters:
        engine.env.filters.update(env_filters)

    return engine
