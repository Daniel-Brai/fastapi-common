import contextvars
from pathlib import Path
from typing import Callable, Sequence

from lib.i18n.exceptions import LocaleNotFoundError
from lib.i18n.loaders import load_file, scan_locale_dir
from lib.i18n.translator import Translator
from lib.i18n.types import LocaleStr, TranslationDict
from lib.i18n.utils import deep_merge

_locale_ctx: contextvars.ContextVar[LocaleStr | None] = contextvars.ContextVar("i18n_locale", default=None)


class I18n:
    """
    Main i18n registry

    Typical usage
    -------------
    ::

        from lib.i18n import I18n, I18nMiddleware

        i18n = I18n(locales_dir="locales", default_locale="en", fallback_locale="en")

        app = FastAPI()
        app.add_middleware(I18nMiddleware, i18n=i18n)

        @app.get("/hello")
        async def hello(t=Depends(i18n.get_dependency())):
            return {"message": t("greeting", name="World")}

    Parameters
    ----------
    default_locale:
        Locale used when none is detected from the request.
    fallback_locale:
        Locale used when a key is missing in the active locale.
        Set to ``None`` to disable fallback.
    locales_dir:
        Path to a directory that is scanned for translation files on init.
    raise_on_missing:
        Propagate :class:`~fastapi_i18n.exceptions.TranslationKeyError` when
        a key is absent (default: ``False`` — returns the raw key).
    locale_negotiators:
        Ordered list of callables that inspect a ``Request`` and return a
        locale string or ``None``.  The first non-``None`` result wins.
        If none succeed, *default_locale* is used.
        The middleware will populate these automatically when you call
        :meth:`add_negotiator`.
    """

    def __init__(
        self,
        default_locale: LocaleStr = "en",
        fallback_locale: LocaleStr | None = "en",
        locales_dir: str | Path | None = None,
        raise_on_missing: bool = False,
        locale_negotiators: list[Callable] | None = None,
    ) -> None:
        self.default_locale = default_locale
        self.fallback_locale = fallback_locale
        self.raise_on_missing = raise_on_missing
        self._translations: dict[LocaleStr, TranslationDict] = {}
        self._negotiators: list[Callable] = list(locale_negotiators or [])

        if locales_dir is not None:
            self.load_from_dir(locales_dir)

    def load_from_dir(self, directory: str | Path) -> None:
        """
        Scan *directory* for translation files and merge them into the registry.

        See :func:`~lib.i18n.loaders.scan_locale_dir` for the expected layout.
        """

        path = Path(directory)
        if not path.is_dir():
            raise NotADirectoryError(f"Locales directory not found: {path}")

        discovered = scan_locale_dir(path)
        self._translations.update(discovered)

    def load_locale(self, locale: LocaleStr, file: str | Path) -> None:
        """
        Load (or merge) a single translation *file* for *locale*.
        """

        existing = self._translations.setdefault(locale, {})
        deep_merge(existing, load_file(Path(file)))

    def add_translations(self, locale: LocaleStr, data: TranslationDict) -> None:
        """
        Programmatically register translation *data* for *locale*
        """

        existing = self._translations.setdefault(locale, {})
        deep_merge(existing, data)

    def add_negotiator(self, fn: Callable) -> None:
        """
        Register a locale-negotiator callable.

        The callable receives a :class:`starlette.requests.Request` and
        should return a :class:`str` locale code or ``None``.
        """
        self._negotiators.append(fn)

    def negotiate_locale(self, request: object) -> LocaleStr:
        """
        Run negotiators in order and return the first resolved locale.

        Falls back to :attr:`default_locale`.
        """
        for negotiator in self._negotiators:
            result = negotiator(request)
            if result and result in self._translations:
                return result

            # Accept-Language may return e.g. "en-US"; try base language too
            if result:
                base = result.split("-")[0].split("_")[0]
                if base in self._translations:
                    return base

        return self.default_locale

    @property
    def available_locales(self) -> Sequence[LocaleStr]:
        """
        All locales for which translations have been loaded
        """
        return list(self._translations.keys())

    def get_translator(self, locale: LocaleStr | None = None) -> Translator:
        """
        Return a :class:`~lib.i18n.translator.Translator` bound to *locale*.

        If *locale* is ``None``, the value stored in the current
        :mod:`contextvars` context (set by the middleware) is used,
        then :attr:`default_locale`.
        """

        resolved = locale or _locale_ctx.get() or self.default_locale

        if resolved not in self._translations:
            if self.fallback_locale and self.fallback_locale in self._translations:
                resolved = self.fallback_locale
            else:
                raise LocaleNotFoundError(resolved)

        fallback_data: TranslationDict | None = None
        if self.fallback_locale and self.fallback_locale != resolved and self.fallback_locale in self._translations:
            fallback_data = self._translations[self.fallback_locale]

        return Translator(
            locale=resolved,
            translations=self._translations[resolved],
            fallback_translations=fallback_data,
            raise_on_missing=self.raise_on_missing,
        )

    def get_dependency(self) -> Callable[[], Translator]:
        """
        Return a FastAPI dependency factory (for use with ``Depends``).

        Example::

            @app.get("/")
            async def root(t=Depends(i18n.get_dependency())):
                return {"msg": t("welcome")}
        """

        i18n_instance = self

        def _dependency() -> Translator:
            return i18n_instance.get_translator()

        return _dependency

    @staticmethod
    def set_locale(locale: LocaleStr) -> contextvars.Token:
        """
        Set the active locale in the current async context.
        """
        return _locale_ctx.set(locale)

    @staticmethod
    def get_current_locale() -> LocaleStr | None:
        """
        Return the locale stored in the current async context
        """
        return _locale_ctx.get()

    @staticmethod
    def reset_locale(token: contextvars.Token) -> None:
        """
        Reset the locale context variable to its previous state
        """
        _locale_ctx.reset(token)


def get_translator() -> Translator:
    """
    Return the active :class:`~lib.i18n.translator.Translator` from context.

    Requires that :class:`~lib.i18n.middleware.I18nMiddleware` (or equivalent)
    has stored an instance via :data:`_locale_ctx`.

    Raises ``RuntimeError`` if no middleware has been configured.
    """

    locale = _locale_ctx.get()
    if locale is None:
        raise RuntimeError("No active locale found in context.  " "Did you add I18nMiddleware to your FastAPI app?")

    raise RuntimeError(
        "Use i18n.get_translator() or Depends(i18n.get_dependency()) instead of " "the bare get_translator() helper."
    )
