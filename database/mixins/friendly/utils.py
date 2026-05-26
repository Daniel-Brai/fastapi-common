import re
import unicodedata
from typing import Callable


def slugify(value: str, *, separator: str = "-", allow_unicode: bool = False) -> str:
    """
    Convert *value* into a URL-safe slug.

    Steps
    -----
    1. Normalise unicode (NFKC).
    2. If allow_unicode is False, encode to ASCII and ignore un-encodable chars.
    3. Lower-case.
    4. Replace whitespace / hyphens / underscores with *separator*.
    5. Remove remaining characters that are not alphanumeric (or unicode word
       chars when allow_unicode=True) or the separator.
    6. Collapse consecutive separators and strip leading/trailing separators.
    """

    value = str(value)
    value = unicodedata.normalize("NFKC", value)

    if not allow_unicode:
        value = value.encode("ascii", "ignore").decode("ascii")

    value = value.lower()
    value = re.sub(r"[\s\-_]+", separator, value)

    safe_sep = re.escape(separator)
    if allow_unicode:
        # Keep unicode word characters (letters, digits, _) plus our separator
        value = re.sub(rf"[^\w{safe_sep}]", "", value, flags=re.UNICODE)
        # \w includes underscore — replace bare underscores that aren't the separator
        if separator != "_":
            value = re.sub(r"_+", separator, value)
    else:
        value = re.sub(rf"[^a-z0-9{safe_sep}]", "", value)

    value = re.sub(rf"{safe_sep}+", separator, value)
    return value.strip(separator)


def truncate_slug(slug: str, max_length: int, separator: str) -> str:
    """
    Prune *slug* to fit within *max_length* without cutting off the separator.

    If slug is already short enough, return as is.
    """

    if len(slug) <= max_length:
        return slug

    return slug[:max_length].rstrip(separator)


def make_unique_slug(
    candidate: str,
    *,
    exists: Callable[[str], bool],
    separator: str = "-",
    max_length: int = 255,
    start: int = 2,
) -> str:
    """
    Ensure *candidate* is unique by appending a suffix if needed.
    """

    if not exists(candidate):
        return candidate

    counter = start
    while True:
        suffix = f"{separator}{counter}"
        base = candidate[: max_length - len(suffix)].rstrip(separator)
        slug = f"{base}{suffix}"
        if not exists(slug):
            return slug

        counter += 1
