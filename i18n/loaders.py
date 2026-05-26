import json
from pathlib import Path
from typing import Any

from lib.i18n.types import TranslationDict
from lib.i18n.utils import deep_merge


def _load_toml_module() -> Any:
    try:
        import tomllib

        return tomllib
    except ImportError:
        pass
    try:
        import tomli as tomllib  # type: ignore[no-reattr]

        return tomllib
    except ImportError:
        return None


_TOML = _load_toml_module()


def load_json(path: Path) -> TranslationDict:
    """
    Load a JSON translation file.
    """
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_toml(path: Path) -> TranslationDict:
    """
    Load a TOML translation file
    """
    if _TOML is None:
        raise ImportError(
            "TOML support requires Python 3.11+ or the 'tomli' package. " "Install it with: pip install tomli"
        )
    with path.open("rb") as fh:
        return _TOML.load(fh)


def load_file(path: Path) -> TranslationDict:
    """
    Dispatch to the correct loader based on file extension.
    """

    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)

    if suffix == ".toml":
        return load_toml(path)

    raise ValueError(f"Unsupported translation file format '{suffix}'. " "Supported formats: .json, .toml")


def scan_locale_dir(locale_dir: Path) -> dict[str, TranslationDict]:
    """
    Scan *locale_dir* for translation files.

    Expected layout (two variants are supported):

    Flat layout
    -----------
    locales/
      en.json
      fr.json
      pt-BR.toml

    Per-locale subdirectory layout
    --------------------------------
    locales/
      en/
        messages.json
        errors.json
      fr/
        messages.json

    In the subdirectory layout all files inside a locale folder are
    deep-merged into a single dict keyed by the directory name.

    Returns
    -------
    Dict mapping locale codes with merged TranslationDict.
    """

    translations: dict[str, TranslationDict] = {}

    for entry in sorted(locale_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in (".json", ".toml"):
            locale = entry.stem
            translations[locale] = load_file(entry)

        elif entry.is_dir():
            locale = entry.name
            merged: TranslationDict = {}

            for file in sorted(entry.rglob("*")):
                if file.is_file() and file.suffix.lower() in (".json", ".toml"):
                    deep_merge(merged, load_file(file))

            if merged:
                translations[locale] = merged

    return translations
