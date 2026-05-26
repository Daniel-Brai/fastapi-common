from dataclasses import dataclass, field


@dataclass
class SlugConfig:
    """
    Configuration for slug generation on a model.

    Attributes:
        from_fields:    One or more model field names to derive the slug from.
                        Values are joined with a separator before slugifying.
        separator:      Word separator in the generated slug. Default: "-".
        max_length:     Slug is truncated to this length before uniqueness
                        resolution. Default: 255.
        allow_unicode:  When True, non-ASCII characters are preserved instead
                        of being transliterated. Default: False.
        slug_field:     Name of the column that stores the slug. Default: "slug".
        update_on_change: Regenerate the slug whenever the source fields change.
                        Default: False (slug is set once at INSERT time).
    """

    from_fields: list[str] = field(default_factory=list)
    separator: str = "-"
    max_length: int = 255
    allow_unicode: bool = False
    slug_field: str = "slug"
    update_on_change: bool = False
