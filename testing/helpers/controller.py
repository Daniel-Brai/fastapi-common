from typing import Any, Type

from fastapi import FastAPI


def build_app(
    controller_class: Type[Any],
    *,
    only: list[str] | None = None,
    exclude: list[str] | None = None,
) -> FastAPI:
    """
    Construct a minimal FastAPI app that mounts only *controller_class*.
    """

    app = FastAPI(title="test")

    from lib.ext.fastapi import Controller

    if issubclass(controller_class, Controller):
        controller_class.register(app, only=only, exclude=exclude)
    else:
        raise ValueError(f"{controller_class.__class__.__name__} is not an instance of `Controller`")

    return app
