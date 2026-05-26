from fastapi import APIRouter, Form, Response, status


def get_i18n_router(
    router_prefix: str = "/i18n",
    locale_cookie_name: str = "locale",
) -> APIRouter:
    """
    Get an APIRouter with i18n-related endpoints.
    """

    i18n_router = APIRouter(prefix=router_prefix)

    @i18n_router.post(
        "/change-language",
        include_in_schema=False,
    )
    async def change_language(
        language: str = Form(..., description="The locale code to switch to, e.g. 'en' or 'fr'.")
    ) -> Response:
        """
        Change the user's preferred language.

        This endpoint is intended to be used with a form that allows users to
        select their preferred language.

        The selected language will be stored in a cookie and used for subsequent requests.
        """

        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.set_cookie(
            key=locale_cookie_name,
            value=language,
            max_age=60 * 60 * 24 * 365,  # 1 year
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    return i18n_router
