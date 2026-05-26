import re
from typing import Any

from lib.i18n.exceptions import TranslationKeyError
from lib.i18n.types import LocaleStr, TranslationDict

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class Translator:
    """
    Bound to a single locale.  Obtained via :meth:`I18n.get_translator`.

    Parameters
    ----------
    locale:
        Active locale code (e.g. ``"en"``, ``"pt-BR"``).
    translations:
        Merged dict for this locale.
    fallback_translations:
        Dict for the fallback locale; ``None`` if not configured.
    raise_on_missing:
        If ``True``, raise :class:`TranslationKeyError` when a key is absent
        from both the active and fallback translations.
        If ``False``, return the raw key string instead.
    """

    def __init__(
        self,
        locale: LocaleStr,
        translations: TranslationDict,
        fallback_translations: TranslationDict | None = None,
        raise_on_missing: bool = False,
    ) -> None:
        self.locale = locale
        self._translations = translations
        self._fallback = fallback_translations
        self._raise_on_missing = raise_on_missing

    def __call__(self, key: str, **kwargs: Any) -> str:
        """
        Shorthand for :meth:`translate`
        """
        return self.translate(key, **kwargs)

    def translate(self, key: str, **kwargs: Any) -> str:
        """
        Resolve *key* and interpolate *kwargs*.

        Dot notation is supported for nested dicts::

            t("errors.auth.forbidden")

        Pluralisation
        ~~~~~~~~~~~~~
        If the resolved value is a dict, ``count`` is used to pick the
        plural form.  The dict may contain any subset of these keys
        (checked in order): ``"zero"``, ``"one"``, ``"other"``::

            # translation file:
            # { "apples": { "zero": "no apples", "one": "one apple", "other": "{count} apples" } }

            t("apples", count=0)   # → "no apples"
            t("apples", count=1)   # → "one apple"
            t("apples", count=5)   # → "5 apples"
        """

        raw = self._resolve(key)

        if isinstance(raw, dict):
            raw = self._pluralize(raw, kwargs.get("count", 0), key)

        if not isinstance(raw, str):
            raw = str(raw)

        return self._interpolate(raw, kwargs)

    def get(self, key: str, default: str | None = None, **kwargs: Any) -> str | None:
        """
        Like :meth:`translate` but returns *default* on missing keys.
        """

        try:
            return self.translate(key, **kwargs)
        except (TranslationKeyError, KeyError):
            return default

    def _resolve(self, key: str) -> Any:
        """
        Walk dot-path in active translations, then fallback.
        """
        value = _dot_get(self._translations, key)
        if value is None and self._fallback is not None:
            value = _dot_get(self._fallback, key)

        if value is None:
            if self._raise_on_missing:
                raise TranslationKeyError(key, self.locale)

            return key

        return value

    def _pluralize(self, forms: dict, count: Any, key: str) -> str:
        """
        Select a plural form from a dict of plural forms.
        """

        try:
            n = int(count)
        except (TypeError, ValueError):
            n = 0

        if n == 0 and "zero" in forms:
            return forms["zero"]
        if n == 1 and "one" in forms:
            return forms["one"]
        if "other" in forms:
            return forms["other"]

        # Last resort: first value in the dict
        return next(iter(forms.values()), key)

    @staticmethod
    def _interpolate(template: str, kwargs: dict) -> str:
        """
        Replace ``{name}`` placeholders with values from *kwargs*.
        """

        if not kwargs:
            return template

        def replacer(match: re.Match) -> str:  # type: ignore[type-arg]
            name = match.group(1)
            return str(kwargs[name]) if name in kwargs else match.group(0)

        return _PLACEHOLDER_RE.sub(replacer, template)


def _dot_get(data: dict, key: str) -> Any:
    """
    Retrieve a value from a nested dict using dot-notation *key*.

    Example:
    >>> data = {"a": {"b": {"c": 42}}}
    >>> _dot_get(data, "a.b.c")
    42
    >>> _dot_get(data, "a.b.x") is None
    True
    >>> _dot_get(data, "a.x.c") is None
    True
    """

    parts = key.split(".")
    current: Any = data

    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None

        current = current[part]

    return current
