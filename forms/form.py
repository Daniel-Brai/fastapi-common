import asyncio
import importlib
import inspect
import json
from html import escape
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from markupsafe import Markup
from pydantic import ValidationError
from starlette_async_jinja import AsyncJinja2Templates

from lib.forms.base import BaseForm
from lib.forms.exceptions import FormConfigError, FormNotFoundError, FormServiceError, FormTemplateNotFoundError
from lib.forms.schemas import FormConfig
from lib.logger import get_logger
from lib.templates import TemplateEngine

logger = get_logger("lib.forms.form")


class Form:
    """
    Factory for discovering, rendering, and handling submissions for :class:`~forms.base.BaseForm`
    subclasses.

    Args:
        app:
            The running :class:`fastapi.FastAPI` application instance.

        template_engine:
            A ``Jinja2Templates`` **or** ``AsyncJinja2Templates`` instance.
            The class is detected automatically; async rendering is used when
            ``AsyncJinja2Templates`` is supplied.

        components:
            Mapping of *field-type key* → *template path relative to the
            template directory configured in the engine*.  Every key referenced
            by a :func:`~forms.fields.FormField` call must appear here.

            Example::

                {
                    "text":     "components/forms/inputs/text.html",
                    "email":    "components/forms/inputs/email.html",
                    "password": "components/forms/inputs/password.html",
                    "select":   "components/forms/inputs/select.html",
                }

        modules:
            List of Python module paths to scan for :class:`~forms.base.BaseForm`
            subclasses.  Only classes *defined* in the given module (not merely
            imported into it) are registered.

            Example::

                ["app.domain.forms.auth", "app.domain.forms.account"]

        route_prefix:
            URL prefix for auto-generated routes (default ``"~/forms"``).

        use_i18n:
            If ``True``, the form will look for a translation function ``_t`` in
            the Jinja environment globals and use it to translate button text and
            any text in the form config marked for translation.

    **Auto-generated routes** (registered as ``include_in_schema=False``)::

        GET  {route_prefix}/{form_name}                            → render form HTML
        POST {route_prefix}/{form_name}/submit                     → handle submission
        POST {route_prefix}/{form_name}/fields/{field_name}/validate → inline validation

    **Jinja2 globals** added to the template environment::

        {{ render_form("login_form") }}
        {{ render_form_field("login_form", "email") }}

    Both globals return :class:`~markupsafe.Markup` so you do **not** need the
    ``| safe`` filter.

    Usage::

        from fastapi import FastAPI
        from fastapi.templating import Jinja2Templates
        from forms import Form

        app = FastAPI()
        templates = Jinja2Templates(directory="views")

        form = Form(
            app=app,
            template_engine=templates,
            components={
                "text":  "components/forms/inputs/text.html",
                "email": "components/forms/inputs/email.html",
            },
            modules=["app.domain.forms.auth"],
        )
    """

    def __init__(
        self,
        app: FastAPI,
        template_engine: TemplateEngine,
        components: dict[str, str],
        modules: list[str],
        route_prefix: str = "/forms",
        use_i18n: bool = False,
    ) -> None:
        self.app = app
        self.template_engine = template_engine
        self.components = components
        self.route_prefix = route_prefix.rstrip("/")
        self._is_async: bool = isinstance(template_engine, AsyncJinja2Templates)
        self._registry: dict[str, type[BaseForm]] = {}
        self._use_i18n = use_i18n

        self._discover_forms(modules)
        self._validate_components()
        self._register_routes()
        self._setup_jinja_globals()
        self._check_if_i18n_available()

    def _check_if_i18n_available(self) -> None:
        if self._use_i18n:
            env = self.template_engine.env
            if "_t" not in env.globals:
                raise FormConfigError(
                    "Forms: i18n is enabled but no '_t' function found in template globals. "
                    "Make sure to add your translation function to the Jinja environment globals."
                )

    def _discover_forms(self, modules: list[str]) -> None:
        """
        Import each module in *modules* and register every :class:`BaseForm`
        """
        for module_path in modules:
            try:
                module = importlib.import_module(module_path)
            except ImportError as exc:
                logger.warning("Forms: cannot import module '%s': %s", module_path, exc)
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseForm) and obj is not BaseForm and obj.__module__.startswith(module.__name__):
                    name = obj.get_form_name()
                    self._registry[name] = obj
                    logger.debug("Forms: registered '%s' from '%s'", name, module_path)

    def _validate_components(self) -> None:
        """
        Verify that every component template path in ``self.components`` resolves
        to an existing file on disk.

        Raises :exc:`FormTemplateNotFoundError` immediately so misconfiguration is caught at startup.
        """

        loader = self.template_engine.env.loader
        search_paths: list[str] = list(getattr(loader, "searchpath", []))

        for field_type, rel_path in self.components.items():
            found = any((Path(sp) / rel_path).is_file() for sp in search_paths)
            if not found:
                checked = " | ".join(str(Path(sp) / rel_path) for sp in search_paths)
                raise FormTemplateNotFoundError(field_type, checked or rel_path)

    def get_form(self, form_name: str) -> type[BaseForm]:
        """
        Retrieve a registered form class by name, raising :exc:`FormNotFoundError` if absent.
        """

        form_class = self._registry.get(form_name)
        if form_class is None:
            raise FormNotFoundError(form_name)

        return form_class

    async def render_form(
        self,
        form_name: str,
        values: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
        html_attrs_overrides: dict[str, dict[str, Any] | Any] | None = None,
        config_overrides: dict[str, Any] | None = None,
        context: Any | None = None,
    ) -> str:
        form_class = self.get_form(form_name)
        config = form_class.get_form_config()

        parts: list[str] = []

        for field_name in form_class.model_fields:
            parts.append(
                await self.render_form_field(
                    form_name,
                    field_name,
                    value=(values or {}).get(field_name),
                    error=(errors or {}).get(field_name),
                    html_attrs_overrides=html_attrs_overrides,
                )
            )

        if config_overrides is not None:

            if (
                "submit_url" in config_overrides
                and config_overrides.get("submit_url") is not None
                and config.submit_url is not None
            ):
                config.submit_url = config.submit_url.format(**config_overrides["submit_url"])

        parts.append(self._build_buttons_html(config))
        cancel_restore_html = await self._render_cancel_restore_html_async(config.cancel_restore_html)
        return self._wrap_form(
            form_name,
            config,
            "".join(parts),
            context,
            cancel_restore_html=cancel_restore_html,
        )

    async def render_form_cls(
        self,
        form: BaseForm,
        errors: dict[str, str] | None = None,
        html_attrs_overrides: dict[str, dict[str, Any] | Any] | None = None,
        config_overrides: dict[str, Any] | None = None,
        context: Any | None = None,
    ) -> str:
        form_name = form.__class__.get_form_name()
        form_class = self.get_form(form_name)
        config = form_class.get_form_config()
        values = form.model_dump()

        parts: list[str] = []
        for field_name in form_class.model_fields:
            parts.append(
                await self.render_form_field(
                    form_name,
                    field_name,
                    value=values.get(field_name),
                    error=(errors or {}).get(field_name),
                    html_attrs_overrides=html_attrs_overrides,
                )
            )

        if config_overrides is not None:
            if (
                "submit_url" in config_overrides
                and config_overrides.get("submit_url") is not None
                and config.submit_url is not None
            ):
                config.submit_url = config.submit_url.format(**config_overrides["submit_url"])

        parts.append(self._build_buttons_html(config))
        cancel_restore_html = await self._render_cancel_restore_html_async(config.cancel_restore_html)
        return self._wrap_form(
            form_name,
            config,
            "".join(parts),
            context,
            cancel_restore_html=cancel_restore_html,
        )

    def _render_form_cls_sync(
        self,
        form: BaseForm,
        errors: dict[str, str] | None = None,
        html_attrs_overrides: dict[str, dict[str, Any] | Any] | None = None,
        config_overrides: dict[str, Any] | None = None,
        context: Any | None = None,
    ) -> str:
        form_name = form.__class__.get_form_name()
        form_class = self.get_form(form_name)
        config = form_class.get_form_config()
        values = form.model_dump()

        parts: list[str] = []
        for field_name in form_class.model_fields:
            parts.append(
                self._render_form_field_sync(
                    form_name,
                    field_name,
                    value=values.get(field_name),
                    error=(errors or {}).get(field_name),
                    html_attrs_overrides=html_attrs_overrides,
                )
            )

        if config_overrides is not None:
            if (
                "submit_url" in config_overrides
                and config_overrides.get("submit_url") is not None
                and config.submit_url is not None
            ):
                config.submit_url = config.submit_url.format(**config_overrides["submit_url"])

        parts.append(self._build_buttons_html(config))
        cancel_restore_html = self._render_cancel_restore_html_sync(config.cancel_restore_html)
        return self._wrap_form(
            form_name,
            config,
            "".join(parts),
            context,
            cancel_restore_html=cancel_restore_html,
        )

    async def render_form_field(
        self,
        form_name: str,
        field_name: str,
        value: Any = None,
        error: str | None = None,
        html_attrs_overrides: dict[str, dict[str, Any] | Any] | None = None,
    ) -> str:
        """
        Render a single form field using its registered component template.

        Args:
            form_name (str):  The form this field belongs to.
            field_name (str): Python attribute name of the field.
            value (Any): Current value to pre-fill the input.
            error (str | None): Validation error message to display beneath the input.

        Returns:
            Raw HTML string for the field.
        """

        context = self._build_field_context(form_name, field_name, value, error, html_attrs_overrides)
        tpl = self._resolve_field_template(form_name, field_name)
        return await self._render_template(tpl, context)

    def _render_form_sync(
        self,
        form_name: str,
        values: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
        context: Any | None = None,
    ) -> str:
        form_class = self.get_form(form_name)
        config = form_class.get_form_config()

        parts: list[str] = []

        for field_name in form_class.model_fields:
            parts.append(
                self._render_form_field_sync(
                    form_name,
                    field_name,
                    value=(values or {}).get(field_name),
                    error=(errors or {}).get(field_name),
                )
            )

        parts.append(self._build_buttons_html(config))
        cancel_restore_html = self._render_cancel_restore_html_sync(config.cancel_restore_html)
        return self._wrap_form(
            form_name,
            config,
            "".join(parts),
            context,
            cancel_restore_html=cancel_restore_html,
        )

    def _render_form_field_sync(
        self,
        form_name: str,
        field_name: str,
        value: Any = None,
        error: str | None = None,
        html_attrs_overrides: dict[str, dict[str, Any] | Any] | None = None,
    ) -> str:
        context = self._build_field_context(form_name, field_name, value, error, html_attrs_overrides)
        tpl = self._resolve_field_template(form_name, field_name)
        return self._render_template_sync(tpl, context)

    def _build_field_context(
        self,
        form_name: str,
        field_name: str,
        value: Any = None,
        error: str | None = None,
        html_attrs_overrides: dict[str, dict[str, Any] | Any] | None = None,
    ) -> dict[str, Any]:

        form_class = self.get_form(form_name)
        fi = form_class.model_fields.get(field_name)
        if fi is None:
            raise ValueError(f"Field '{field_name}' not found in form '{form_name}'.")

        meta = form_class.get_field_form_meta(field_name)
        html_attrs: dict[str, Any] = dict(meta.get("html_attrs") or {})

        if self._use_i18n:
            _t = self.template_engine.env.globals.get("_t", lambda x, **kwargs: x)
            for k in ["label", "placeholder", "options_placeholder"]:
                if k in html_attrs and isinstance(html_attrs[k], str) and "." in html_attrs[k]:
                    html_attrs[k] = str(_t(html_attrs[k]))

            if "options" in html_attrs and isinstance(html_attrs["options"], list):
                for opt in html_attrs["options"]:
                    if isinstance(opt, dict) and "text" in opt and isinstance(opt["text"], str) and "." in opt["text"]:
                        opt["text"] = str(_t(opt["text"]))

            if "options" in html_attrs and isinstance(html_attrs["options"], list):
                for opt in html_attrs["options"]:
                    if isinstance(opt, dict) and "text" in opt and isinstance(opt["text"], str) and "." in opt["text"]:
                        opt["text"] = str(_t(opt["text"]))

        if self._use_i18n:
            _t = self.template_engine.env.globals.get("_t", lambda x, **kwargs: x)
            for k in ["label", "placeholder", "options_placeholder"]:
                if k in html_attrs and isinstance(html_attrs[k], str) and "." in html_attrs[k]:
                    html_attrs[k] = str(_t(html_attrs[k]))

            if "options" in html_attrs and isinstance(html_attrs["options"], list):
                for opt in html_attrs["options"]:
                    if isinstance(opt, dict) and "text" in opt and isinstance(opt["text"], str) and "." in opt["text"]:
                        opt["text"] = str(_t(opt["text"]))

            if "options" in html_attrs and isinstance(html_attrs["options"], list):
                for opt in html_attrs["options"]:
                    if isinstance(opt, dict) and "text" in opt and isinstance(opt["text"], str) and "." in opt["text"]:
                        opt["text"] = str(_t(opt["text"]))

        config = form_class.get_form_config()
        config_overrides: dict[str, Any] = meta.get("config_overrides") or {}
        input_name = fi.alias or field_name

        inline_validation = config_overrides.get("inline_validation", config.inline_validation)

        if inline_validation:
            delay_sec = config_overrides.get(
                "inline_validation_threshold_seconds",
                config.inline_validation_threshold_seconds,
            )
            delay_ms = delay_sec * 1000
            html_attrs.update(
                {
                    "hx-post": (f"{self.route_prefix}/{form_name}" f"/fields/{field_name}/validate"),
                    "hx-trigger": f"change, keyup changed delay:{delay_ms}ms",
                    "hx-target": f"#{field_name}-error",
                    "hx-swap": "innerHTML",
                    "hx-include": "closest form",
                }
            )

        if html_attrs_overrides and field_name in html_attrs_overrides:
            overrides = html_attrs_overrides[field_name]
            html_attrs.update(overrides)

        default_option_value = None
        options = html_attrs.get("options")
        if isinstance(options, list):
            for opt in options:
                if isinstance(opt, dict) and opt.get("default"):
                    default_option_value = opt.get("value")
                    break
                elif isinstance(opt, (list, tuple)) and len(opt) >= 3 and opt[2] is True:
                    default_option_value = opt[0]
                    break

        field_dict = {
            **html_attrs,
            "name": input_name,
            "value": value,
            "error": error,
            "required": html_attrs.get("required", fi.is_required()),
        }
        if default_option_value is not None:
            field_dict["default_option_value"] = default_option_value

        return {
            "form": {"name": form_name},
            "field": field_dict,
        }

    def _resolve_field_template(self, form_name: str, field_name: str) -> str:

        form_class = self.get_form(form_name)
        meta = form_class.get_field_form_meta(field_name)
        field_type: str = meta.get("field_type", "text")
        tpl = self.components.get(field_type)

        if tpl is None:
            raise FormTemplateNotFoundError(
                field_type,
                f"<field_type '{field_type}' is not listed in the components dict>",
            )

        return tpl

    async def _render_template(self, tpl: str, ctx: dict[str, Any]) -> str:
        if self._is_async:
            async_engine = cast(AsyncJinja2Templates, self.template_engine)
            return await async_engine.render_block(tpl, **ctx)

        return self._render_template_sync(tpl, ctx)

    def _render_template_sync(self, template_path: str, context: dict[str, Any]) -> str:
        tpl = self.template_engine.env.get_template(template_path)
        return tpl.render(**context)

    def _build_buttons_html(self, config: FormConfig) -> str:
        container_attrs = config.buttons.buttons_container_html_attrs or {}
        container_str = " ".join(f'{k}="{escape(str(v))}"' for k, v in container_attrs.items())

        btns_list = []
        for b in config.buttons.buttons:
            attrs = []
            _t = self.template_engine.env.globals.get("_t", lambda x, **kwargs: x)
            translate_attr_values = self._use_i18n
            for k, v in b.get("html_attrs", {}).items():
                if k == "htmx-attrs":
                    if isinstance(v, list):
                        attrs.extend(str(item) for item in v)
                    else:
                        attrs.append(str(v))
                else:
                    value = str(v)
                    if translate_attr_values and isinstance(v, str) and "." in v:
                        value = str(_t(v))
                    attrs.append(f'{k}="{escape(value)}"')

            attrs_str = " ".join(attrs)
            text = b.get("text_or_html", "Submit")

            if self._use_i18n:
                _t = self.template_engine.env.globals.get("_t", lambda x, **kwargs: x)
                if "{{" in text or "{%" in text:
                    try:
                        import re

                        text = re.sub(
                            r"\{\{\s*_t\(\s*['\"](.*?)['\"]\s*\)\s*\}\}",
                            lambda m, _t=_t: str(_t(m.group(1))),
                            text,
                        )
                    except Exception as e:
                        logger.debug(
                            "Forms: Failed to extract translation key from button text: %s",
                            e,
                        )
                else:
                    pass

            btns_list.append(f"<button {attrs_str}>{text}</button>")

        btns = "".join(btns_list)
        return f"<div {container_str}>{btns}</div>" if container_str else btns

    def _wrap_form(
        self,
        form_name: str,
        config: FormConfig,
        inner_html: str,
        context: Any | None = None,
        cancel_restore_html: str | None = None,
    ) -> str:
        if config.submit_service:
            action = f"{self.route_prefix}/{form_name}/submit"
            method = "post"
        else:
            action = config.submit_url
            method = config.submit_method.lower()

        attrs: list[str] = [
            f'id="{form_name}"',
        ]

        if config.use_htmx:
            attrs.extend(
                [
                    f'hx-{method}="{action}"',
                    f'hx-target="{config.target or f"#{form_name}"}"',
                    f'hx-swap="{config.swap}"',
                    f'hx-trigger="{config.trigger}"',
                ]
            )
        else:
            attrs.extend(
                [
                    f'action="{action}"',
                    f'method="{method}"',
                ]
            )

        if context and "csrf_header" in context:
            kwargs_json = json.dumps(context["csrf_header"])
            attrs.append(f"hx-headers='{escape(kwargs_json)}'")

        if config.with_credentials:
            attrs.append(f'hx-request="{json.dumps({"credentials": True})}"')

        if config.encoding == "multipart/form-data":
            attrs.append('enctype="multipart/form-data"')
        else:
            if config.use_htmx:
                attrs.append('hx-ext="form-json"')
            else:
                attrs.append('enctype="application/x-www-form-urlencoded"')

        if config.submit_context:
            _t = self.template_engine.env.globals.get("_t", lambda x, **kwargs: x) if self._use_i18n else lambda x: x

            def _translate_strings(value: Any) -> Any:
                if isinstance(value, str) and value and not value.startswith("{") and "." in value:
                    return str(_t(value))
                if isinstance(value, dict):
                    return {k: _translate_strings(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [_translate_strings(item) for item in value]
                return value

            def _translate_ctx_dict(d: dict) -> dict:
                d = dict(d)
                if "context" in d and isinstance(d["context"], dict):
                    d["context"] = _translate_strings(d["context"])
                if "fallback" in d and isinstance(d["fallback"], dict):
                    d["fallback"] = _translate_strings(d["fallback"])
                return d

            if s := config.submit_context.get("success"):
                s_dict = _translate_ctx_dict(dict(s))
                attrs.append(f'data-success-context="{escape(json.dumps(s_dict))}"')
            if e := config.submit_context.get("error"):
                e_dict = _translate_ctx_dict(dict(e))
                attrs.append(f'data-error-context="{escape(json.dumps(e_dict))}"')

        if config.cancel_target:
            attrs.append(f'data-cancel-target="{escape(config.cancel_target)}"')

        if config.css:
            attrs.append(f'class="{escape(config.css)}"')

        cancel_restore_html = cancel_restore_html if cancel_restore_html is not None else config.cancel_restore_html
        if cancel_restore_html:
            attrs.append(f'data-cancel-restore="{escape(cancel_restore_html)}"')

        if config.submit_on_page_load:
            attrs.append('data-submit-on-page-load="true"')

        return f'<form {" ".join(attrs)}>{inner_html}</form>'

    async def _render_cancel_restore_html_async(self, rest_html: str | None) -> str | None:
        if rest_html is None:
            return None

        if self._use_i18n and ("{{" in rest_html or "{%" in rest_html or "_t(" in rest_html):
            _t_func = self.template_engine.env.globals.get("_t", lambda x, **kw: x)
            try:
                tmpl = self.template_engine.env.from_string(rest_html)
                if hasattr(tmpl, "render_async"):
                    return await tmpl.render_async(_t=_t_func)
                return tmpl.render(_t=_t_func)
            except Exception as ex:
                logger.error(f"Failed to render cancel_restore_html template: {ex}")

        return rest_html

    def _render_cancel_restore_html_sync(self, rest_html: str | None) -> str | None:
        if rest_html is None:
            return None

        if self._use_i18n and ("{{" in rest_html or "{%" in rest_html or "_t(" in rest_html):
            _t_func = self.template_engine.env.globals.get("_t", lambda x, **kw: x)
            try:
                tmpl = self.template_engine.env.from_string(rest_html)
                if hasattr(tmpl, "render"):
                    return tmpl.render(_t=_t_func)
                if hasattr(tmpl, "render_async"):
                    return asyncio.run(tmpl.render_async(_t=_t_func))
            except Exception as ex:
                logger.error(f"Failed to render cancel_restore_html template: {ex}")

        return rest_html

    def _register_routes(self) -> None:
        for form_name, form_class in self._registry.items():
            self._add_form_routes(form_name, form_class)

    def _add_form_routes(self, form_name: str, form_class: type[BaseForm]) -> None:
        config = form_class.get_form_config()
        prefix = self.route_prefix
        _self = self

        async def _get_form(request: Request) -> HTMLResponse:
            """
            Render the form for initial display or after a submission error.
            """
            raw_params = dict(request.query_params)
            values = {}
            html_attrs_overrides = {}
            config_overrides = {}

            for key, val in raw_params.items():
                if key.startswith("_attrs_"):
                    field_name = key[7:]
                    try:
                        html_attrs_overrides[field_name] = json.loads(val)
                    except json.JSONDecodeError:
                        logger.warning(f"Form: Invalid JSON for HTML attrs of field '{field_name}': {val}")
                elif key.startswith("_config_"):
                    config_field = key[8:]
                    if config_field.startswith("submit_url__format"):
                        # Since I need form to be dynamic, we enable for formatting
                        try:
                            config_overrides["submit_url"] = json.loads(val)
                        except json.JSONDecodeError:
                            logger.warning(f"Form: Invalid JSON for Config '{config_field}': {val}")
                else:
                    values[key] = val

            html = await _self.render_form(
                form_name,
                values=values,
                html_attrs_overrides=html_attrs_overrides,
                config_overrides=config_overrides,
            )

            alert_html = _self._render_form_alert_indicator(form_name)
            if alert_html:
                html = alert_html + html

            return HTMLResponse(content=html)

        _get_form.__name__ = f"_form_get_{form_name}"
        self.app.add_api_route(
            f"{prefix}/{form_name}",
            _get_form,
            methods=["GET"],
            response_class=HTMLResponse,
            include_in_schema=False,
        )

        if config.submit_service:

            async def _submit(request: Request) -> Any:
                return await _self._handle_submit(request, form_name, form_class)

            _submit.__name__ = f"_form_submit_{form_name}"
            self.app.add_api_route(
                f"{prefix}/{form_name}/submit",
                _submit,
                methods=["POST"],
                include_in_schema=False,
            )

        async def _validate_field(request: Request, field_name: str) -> HTMLResponse:
            return await _self._handle_field_validation(request, form_name, form_class, field_name)

        _validate_field.__name__ = f"_form_validate_{form_name}"

        field_validation_path = f"{prefix}/{form_name}/fields/{{field_name}}/validate"

        self.app.add_api_route(
            field_validation_path,
            _validate_field,
            methods=["POST"],
            response_class=HTMLResponse,
            include_in_schema=False,
        )

    async def _handle_submit(
        self,
        request: Request,
        form_name: str,
        form_class: type[BaseForm],
    ):
        config = await self._resolve_attributes_if(form_class.get_form_config())

        try:
            if config.encoding == "application/json":
                payload = await request.json()
            else:
                payload = _parse_form_data(await request.form())

            instance = form_class.model_validate(payload)

            schema = instance.to_submit_schema()
            submit_data = schema if schema is not None else instance.model_dump()

            assert config.submit_service is not None

            method = self._resolve_service(config.submit_service)
            # Note I expect the submit service to always return dict or a pydantic object
            if inspect.iscoroutinefunction(method):
                result = await method(submit_data)
            else:
                result = method(submit_data)

            headers = {"X-Form-Submit-Success-Response": json.dumps(_serialize_result(result))}

            html = await self.render_form(form_name)

            return Response(content=html, media_type="text/html", headers=headers)
        except ValidationError as exc:
            errors = _extract_pydantic_errors(exc)
            html = await self.render_form(form_name, errors=errors)
            return Response(
                content=html,
                media_type="text/html",
            )

        except Exception:  # noqa: BLE001
            logger.exception(f"Forms: Unhandled error in submit handler for '{form_name}'")
            msg = "An unexpected error occurred. Please try again later."

            headers = {"X-Form-Submit-Error-Response": json.dumps(_serialize_result({"detail": msg}))}

            html = await self.render_form(form_name)

            return Response(
                content=html,
                media_type="text/html",
                headers=headers,
            )

    @staticmethod
    async def _resolve_attributes_if(config: FormConfig) -> FormConfig:
        if not config.attributes_if:
            return config

        for key, (condition, value) in config.attributes_if.items():
            negated = key.endswith(":not")
            attr_name = key.removesuffix(":not")

            result = await _evaluate_condition(condition)
            should_apply = (not result) if negated else result

            if should_apply:
                setattr(config, attr_name, value)

        return config

    async def _handle_field_validation(
        self,
        request: Request,
        form_name: str,
        form_class: type[BaseForm],
        field_name: str,
    ) -> HTMLResponse:

        empty = HTMLResponse(content=_render_inline_field_errors_html(form_name, field_name, []))
        try:
            raw = await request.form()
            form_class.model_validate(_parse_form_data(raw))
            return empty
        except ValidationError as exc:
            errors = _extract_pydantic_error_lists(exc)
            field_errors = errors.get(field_name, [])
            if not field_errors:
                return empty

            return HTMLResponse(content=_render_inline_field_errors_html(form_name, field_name, field_errors))

        except Exception:  # noqa: BLE001
            return empty

    @staticmethod
    def _resolve_service(service_path: str) -> Any:
        """
        Resolve a dotted path to a callable.

        Supports both module-level functions and class methods::

            "app.services.auth.login"                  # module function
            "app.services.auth.AuthService.login"      # class method

        Raises:
            FormServiceError: if the path cannot be imported or the attribute
                              does not exist.
        """

        try:
            parts = service_path.rsplit(".", 1)
            if len(parts) != 2:
                raise ValueError("Path must have at least two components.")

            module_path, attr_name = parts

            class_parts = module_path.rsplit(".", 1)
            if len(class_parts) == 2:
                try:
                    mod = importlib.import_module(class_parts[0])
                    obj = getattr(mod, class_parts[1])
                    return getattr(obj, attr_name)
                except (ImportError, AttributeError):
                    pass

            mod = importlib.import_module(module_path)
            return getattr(mod, attr_name)
        except Exception as exc:
            logger.error(f"Forms: Failed to resolve service '{service_path}': {exc}")
            raise FormServiceError(service_path, str(exc)) from exc

    def _render_form_alert_indicator(self, form_name: str) -> str:
        indicators = self._get_alert_indicators(form_name)
        if not indicators:
            return ""

        inner = "".join(f'<div id="{indicator}"></div>' for indicator in indicators)
        return (
            '<div style="margin-bottom: 24px; display: flex; flex-direction: column; gap: 16px;">' f"{inner}" "</div>"
        )

    def _get_alert_indicators(self, form_name: str) -> list[str]:
        indicators: list[str] = []
        try:
            ctx = self.get_form(form_name).get_form_config().submit_context or {}
            for bucket in ("success", "error"):
                entry = ctx.get(bucket, {})
                if entry.get("name") == "alert":
                    t = entry.get("context", {}).get("type", bucket)
                    indicators.append(f"{form_name}--alert-{t}")

        except Exception:
            pass

        return indicators

    def _setup_jinja_globals(self) -> None:
        env = self.template_engine.env
        from jinja2 import pass_context

        _self = self

        if self._is_async:

            @pass_context
            async def _render_form_global_async(context: Any, form_name: str, **kwargs: Any) -> Markup:
                form_html = await _self.render_form(form_name, context=context, **kwargs)
                return Markup(form_html)

            @pass_context
            async def _render_form_field_global_async(
                _context: Any,
                form_name: str,
                field_name: str,
                **kwargs: Any,
            ) -> Markup:
                form_field_html = await _self.render_form_field(form_name, field_name, **kwargs)
                return Markup(form_field_html)

            @pass_context
            async def _render_form_cancel_restore_global_async(
                _context: Any, form_name: str, **kwargs: Any  # noqa: ARG001
            ) -> Markup:
                try:
                    form = _self.get_form(form_name)
                    rest_html = form.get_form_config().cancel_restore_html
                except FormNotFoundError:
                    return Markup("")

                if rest_html is None:
                    return Markup("")

                if self._use_i18n and ("{{" in rest_html or "{%" in rest_html or "_t(" in rest_html):
                    _t_func = self.template_engine.env.globals.get("_t", lambda x, **kw: x)
                    try:
                        tmpl = self.template_engine.env.from_string(rest_html)
                        if hasattr(tmpl, "render_async"):
                            rest_html = await tmpl.render_async(_t=_t_func)
                        else:
                            rest_html = tmpl.render(_t=_t_func)
                    except Exception as ex:
                        logger.error(f"Failed to render cancel_restore_html template: {ex}")
                        return Markup("")

                return Markup(rest_html or "")

            @pass_context
            async def _render_form_cls_global_async(_context: Any, form: BaseForm, **kwargs: Any) -> Markup:
                form_html = await _self.render_form_cls(form, **kwargs)
                return Markup(form_html)

            env.globals["render_form"] = _render_form_global_async
            env.globals["render_form_cls"] = _render_form_cls_global_async
            env.globals["render_form_field"] = _render_form_field_global_async
            env.globals["render_form_cancel_restore"] = _render_form_cancel_restore_global_async

        else:

            @pass_context
            def _render_form_global_sync(context: Any, form_name: str, **kwargs: Any) -> Markup:  # noqa: ARG001
                return Markup(_self._render_form_sync(form_name, context=context, **kwargs))

            @pass_context
            def _render_form_field_global_sync(
                _context: Any,
                form_name: str,
                field_name: str,
                **kwargs: Any,
            ) -> Markup:
                return Markup(_self._render_form_field_sync(form_name, field_name, **kwargs))

            @pass_context
            def _render_form_cancel_restore_global_sync(
                _context: Any, form_name: str, **kwargs: Any  # noqa: ARG001
            ) -> Markup:  # noqa: ARG001
                try:
                    form = _self.get_form(form_name)
                    rest_html = form.get_form_config().cancel_restore_html
                except FormNotFoundError:
                    return Markup("")

                if rest_html is None:
                    return Markup("")

                if self._use_i18n and ("{{" in rest_html or "{%" in rest_html or "_t(" in rest_html):
                    _t_func = self.template_engine.env.globals.get("_t", lambda x, **kw: x)
                    try:
                        tmpl = self.template_engine.env.from_string(rest_html)
                        if hasattr(tmpl, "render"):
                            rest_html = tmpl.render(_t=_t_func)
                        elif hasattr(tmpl, "render_async"):
                            rest_html = asyncio.run(tmpl.render_async(_t=_t_func))
                    except Exception as ex:
                        logger.error(f"Failed to render cancel_restore_html template: {ex}")
                        return Markup("")

                return Markup(rest_html or "")

            @pass_context
            def _render_form_cls_global_sync(_context: Any, form: BaseForm, **kwargs: Any) -> Markup:
                return Markup(_self._render_form_cls_sync(form, **kwargs))

            env.globals["render_form"] = _render_form_global_sync
            env.globals["render_form_cls"] = _render_form_cls_global_sync
            env.globals["render_form_field"] = _render_form_field_global_sync
            env.globals["render_form_cancel_restore"] = _render_form_cancel_restore_global_sync

        def form_has_alert(form_name: str) -> bool:
            return bool(_self._get_alert_indicators(form_name))

        def get_form_alert_indicators(form_name: str) -> list[str]:
            return _self._get_alert_indicators(form_name)

        env.globals["form_has_alert"] = form_has_alert
        env.globals["get_form_alert_indicators"] = get_form_alert_indicators


async def _evaluate_condition(condition: Any) -> bool:
    if inspect.iscoroutine(condition):
        return bool(await condition)
    if inspect.iscoroutinefunction(condition):
        return bool(await condition())
    if callable(condition):
        return bool(condition())

    return bool(condition)


def _extract_pydantic_errors(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in exc.errors():
        if loc := e.get("loc", ()):
            out.setdefault(str(loc[-1]), e.get("msg", "Invalid value"))
    return out


def _extract_pydantic_error_lists(exc: ValidationError) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in exc.errors():
        if loc := e.get("loc", ()):
            out.setdefault(str(loc[-1]), []).append(str(e.get("msg", "Invalid value")))

    return out


def _parse_form_data(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.multi_items():
        if key in out:
            if isinstance(out[key], list):
                out[key].append(value)
            else:
                out[key] = [out[key], value]
        else:
            out[key] = value

    return out


def _serialize_result(result: Any) -> dict:
    if result is None:
        return {}

    if hasattr(result, "model_dump"):
        return result.model_dump()

    if isinstance(result, dict):
        return result

    return result


def _render_inline_field_errors_html(form_name: str, field_name: str, errors: list[str]) -> str:
    """
    Returns HTML for inline field errors, plus a script to style the input.
    """
    input_id = f"{form_name}-{field_name}"
    if not errors:
        return f"""
        <div></div>
        <script>
            (function() {{
                const input = document.getElementById('{input_id}');
                if (input) input.classList.remove('fb-input-error');
            }})();
        </script>
        """

    items = "".join(
        f'<li style="display: flex; align-items: center; gap: 5px; list-style-type: none;">'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
        f'fill="currentColor" style="width: 16px; height: 16px; flex-shrink: 0;">'
        f'<path fill-rule="evenodd" '
        f'd="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" '
        f'clip-rule="evenodd" />'
        f"</svg>"
        f'<span style="line-height: 1;"> {escape(error)} </span>'
        f"</li>"
        for error in errors
    )

    error_html = f"""
    <ul style="font-size: 11px; color: #f04a4a; line-height: 1.5; margin: 0; padding: 0; padding-top: 8px; padding-bottom: 8px; display: flex; flex-direction: column; gap: 4px; list-style-type: none;">
        {items}
    </ul>
    """

    script = f"""
    <script>
        (function() {{
            const input = document.getElementById('{input_id}');
            if (input) input.classList.add('fb-input-error');
        }})();
    </script>
    """
    return error_html + script
