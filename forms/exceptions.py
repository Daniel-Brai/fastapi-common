class FormTemplateNotFoundError(Exception):
    """
    Raised when a registered component template path does not exist on disk.

    Checked eagerly at ``Form.__init__`` time so misconfiguration surfaces
    immediately rather than at first render.
    """

    def __init__(self, field_type: str, checked_paths: str) -> None:
        self.field_type = field_type
        self.checked_paths = checked_paths
        super().__init__(f"No template found for field type '{field_type}'.\n" f"Checked: {checked_paths}")


class FormConfigError(RuntimeError):
    """
    Raised when a form is used but the forms system has not been configured on the app or
    when it is not configured correctly. This is a catch-all for various misconfigurations that would prevent
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or "Forms system not configured. " "Make sure to call `configure_forms(app)` during app setup."
        )


class FormNotFoundError(Exception):
    """
    Raised when a form name is not present in the registry.
    """

    def __init__(self, form_name: str) -> None:
        self.form_name = form_name
        super().__init__(f"Form '{form_name}' is not registered. " "Check the `modules` list passed to Form(...).")


class FormServiceError(Exception):
    """
    Raised when a submit_service path cannot be resolved or called.
    """

    def __init__(self, service_path: str, reason: str) -> None:
        self.service_path = service_path
        self.reason = reason
        super().__init__(f"Cannot resolve service '{service_path}': {reason}")
