from typing import Any

# e.g. {"greeting": "Hello, {name}!", "errors": {"not_found": "Not found"}}
type TranslationDict = dict[str, Any]

# BCP 47 locale string, e.g. "en", "en-US", "fr", "pt-BR"
type LocaleStr = str
