import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.logger import get_logger

logger = get_logger("lib.mailer.environment")


class MjmlTemplateEnvironment:
    """
    Wraps a Jinja2 Environment whose template_class renders MJML to HTML.

    Examples:

        env = MjmlTemplateEnvironment(
            templates_dir = "/app/templates/email",
            assets_dir    = "/app/static",
            cache_dir     = "/tmp/mjml_cache",
            auto_reload   = True,
            extra_globals = {"APP_NAME": "MyApp", "APP_URL": "https://..."},
        )
        html = env.render("email_welcome.mjml.html", name="Daniel")
    """

    def __init__(
        self,
        templates_dir: str | Path,
        *,
        assets_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
        auto_reload: bool = False,
        extra_globals: dict[str, Any] | None = None,
    ):
        try:
            import mjml
            from jinja2 import Environment, FileSystemBytecodeCache, FileSystemLoader, Template, select_autoescape
        except ImportError as exc:
            raise ImportError("mjml and jinja2 are required: pip install mjml jinja2") from exc

        self._templates_dir = Path(templates_dir)
        self._assets_dir = Path(assets_dir) if assets_dir else None

        if cache_dir:
            cache_path = Path(cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)
            cache_path.chmod(0o700)
            bytecode_cache = FileSystemBytecodeCache(directory=str(cache_path))
        else:
            bytecode_cache = None

        class _MjmlTemplate(Template):
            def render(self, *args: Any, **kwargs: Any) -> str:
                markup = super().render(*args, **kwargs)
                result = mjml.mjml_to_html(markup)
                if result.errors:
                    from lib.mailer.exceptions import MailerTemplateError

                    raise MailerTemplateError(f"MjmlTemplateEnvironment: MJML compilation errors - {result.errors}")

                return result.html

        class _MjmlEnvironment(Environment):
            template_class = _MjmlTemplate

        env_kwargs: dict[str, Any] = {
            "loader": FileSystemLoader(str(self._templates_dir)),
            "auto_reload": auto_reload,
            "autoescape": select_autoescape(["html", "xml"]),
            "extensions": ["jinja2.ext.do"],
            "trim_blocks": True,
            "lstrip_blocks": True,
            "optimized": True,
            "cache_size": 1000,
        }

        if bytecode_cache:
            env_kwargs["bytecode_cache"] = bytecode_cache

        self._env = _MjmlEnvironment(**env_kwargs)
        self._setup_globals(extra_globals or {})

    def _setup_globals(self, extra: dict[str, Any]) -> None:
        g = self._env.globals

        g["now"] = datetime.now
        g["uuid4"] = uuid4
        g["raw_file"] = self._raw_file
        g["rawjson"] = json.dumps

        self._env.filters["rawjson"] = json.dumps

        g.update(extra)

    def _raw_file(self, relative_path: str, mime_type: str = "image/png") -> str:
        """
        Embed a file as a base64 data URI.

            {{ raw_file('images/logo.png', 'image/png') }}

        Path is relative to the assets_dir passed to MjmlTemplateEnvironment().
        If no assets_dir was configured, raises RuntimeError.
        """

        if self._assets_dir is None:
            from lib.mailer.exceptions import MailerTemplateAssetError

            raise MailerTemplateAssetError(
                "raw_file() is not available: no assets_dir configured in MjmlTemplateEnvironment"
            )

        path = self._assets_dir / relative_path

        try:
            data = base64.b64encode(path.read_bytes()).decode()
            return f"data:{mime_type};base64,{data}"
        except FileNotFoundError:
            logger.warning("MjmlTemplateEnvironment: raw_file asset not found: %s", path)
            return ""

    def render(self, template_name: str, **context: Any) -> str:
        """
        Render a template by name and return the final HTML string.
        """

        from lib.mailer.exceptions import MailerTemplateError

        try:
            tmpl = self._env.get_template(template_name)
            return tmpl.render(**context)
        except Exception as exc:
            logger.exception("MjmlTemplateEnvironment: Failed to render template %r", template_name)
            raise MailerTemplateError(f"Failed to render template {template_name!r}: {exc}") from exc

    def add_global(self, name: str, value: Any) -> None:
        """
        Register an extra global variable after construction
        """
        if name in self._env.globals:
            return

        self._env.globals[name] = value

    def add_filter(self, name: str, fn: Any) -> None:
        """
        Register an extra Jinja2 filter after construction
        """
        if name in self._env.filters:
            return

        self._env.filters[name] = fn
