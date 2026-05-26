from typing import Literal

from pydantic import PositiveInt
from pydantic.dataclasses import dataclass


@dataclass
class AuthOptions:
    """
    Options for authentication and authorization.

    This class is used to configure the authentication and authorization
    behavior of the application. It can be extended in the future to include
    more options as needed.

    Attributes:
        registration_enabled (bool, True): Whether user registration is enabled. If False, only existing users can log in. Default is True.
        magic_links_enabled (bool, False): Whether magic link authentication is enabled. If True, users can request a login link to be sent to their email. Default is False.
        verification_token_style (Literal["link", "otp"], "link"): The style of verification tokens. "link" means the token is sent as part of a URL, while "otp" means the token is a one-time password that must be entered by the user. Default is "link".
        deletion_style (Literal["soft", "hard"], "soft"): The style of user deletion. "soft" means the user is marked as deleted but not removed from the database, allowing for potential recovery. "hard" means the user is permanently removed from the database. Default is "soft".
        deletion_grace_period_days (int, 30): The grace period for soft-deleted users before they are permanently deleted. This is only applicable if `deletion_style` is set to "soft". Default is 30 days.
        throttler_enabled (bool, False):
                Whether request throttling is enabled for authentication endpoints. If True, limits the number of requests to prevent abuse.
                Note :meth:`lib.throttler.configure_throttler` must be configured separately for this to work.
                Default is False.
    """

    registration_enabled: bool = True
    magic_links_enabled: bool = False
    verification_token_style: Literal["link", "otp"] = "link"
    deletion_style: Literal["soft", "hard"] = "soft"
    deletion_grace_period_days: PositiveInt = 30
    throttler_enabled: bool = True
