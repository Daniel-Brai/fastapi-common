FORM_CONFIG_ATTRS: frozenset[str] = frozenset(
    {
        "target",
        "swap",
        "trigger",
        "inline_validation",
        "inline_validation_threshold_seconds",
        "with_credentials",
        "submit_on_page_load",
        "submit_service",
        "submit_url",
        "submit_method",
        "encoding",
        "use_htmx",
        "submit_context",
        "buttons",
        "css",
        "attributes_if",
        "cancel_target",
        "cancel_restore_html",
    }
)


CLIENT_COMPONENTS = frozenset({"toast", "alert", "modal", "no-op"})
