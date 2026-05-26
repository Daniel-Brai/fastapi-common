from typing import TYPE_CHECKING, Callable

from lib.i18n.base import I18n, _locale_ctx

if TYPE_CHECKING:
    from lib.i18n.translator import Translator


async def get_locale() -> str:
    """
    FastAPI dependency that returns the active locale code.

    Requires :class:`~lib.i18n.middleware.I18nMiddleware` to be
    registered so that the locale ContextVar is populated.
    """

    locale = _locale_ctx.get()
    if locale is None:
        raise RuntimeError(
            "No locale found in request context. " "Make sure I18nMiddleware is added to your FastAPI app."
        )

    return locale


def use_locale(i18n: I18n) -> Callable:
    """
    Factory that returns a FastAPI dependency yielding a
    :class:`~lib.i18n.translator.Translator` for the current locale.

    Parameters
    ----------
    i18n:
        Your configured :class:`~lib.i18n.base.I18n` instance.

    Example::

        t_dep = use_locale(i18n)

        @app.get("/hello")
        async def hello(t: Translator = Depends(t_dep)):
            return {"message": t("greeting", name="World")}
    """

    async def _dependency() -> "Translator":
        return i18n.get_translator()

    return _dependency
