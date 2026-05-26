class LocaleNotFoundError(Exception):
    """
    Raised when a requested locale has no loaded translations.
    """

    def __init__(self, locale: str) -> None:
        self.locale = locale
        super().__init__(f"No translations loaded for locale '{locale}'.")


class TranslationKeyError(KeyError):
    """
    Raised when a translation key cannot be resolved and no fallback exists.
    """

    def __init__(self, key: str, locale: str) -> None:
        self.key = key
        self.locale = locale
        super().__init__(f"Translation key '{key}' not found for locale '{locale}'.")
