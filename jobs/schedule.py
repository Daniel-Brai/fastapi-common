from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict, Unpack

from lib.jobs.exceptions import InvalidJobScheduleError


@dataclass
class CronSchedule:
    """
    Standard five-field cron expression or keyword fields


    Examples:

        schedule = cron("0 9 * * *")          # daily at 09:00 UTC
        schedule = cron(hour=9, minute=0)     # same, keyword form
        schedule = cron("*/30 * * * *")       # every 30 minutes
        schedule = cron(minute="0")           # top of every hour
    """

    expr: str | None = None
    second: str = "0"
    minute: str = "*"
    hour: str = "*"
    day: str = "*"
    month: str = "*"
    day_of_week: str = "*"

    def as_apscheduler_kwargs(self) -> dict[str, Any]:
        if self.expr:
            parts = self.expr.split()
            if len(parts) != 5:
                raise InvalidJobScheduleError(f"Invalid job schedule cron expression: {self.expr!r}")

            minute, hour, day, month, dow = parts
            return {
                "trigger": "cron",
                "minute": minute,
                "hour": hour,
                "day": day,
                "month": month,
                "day_of_week": dow,
                "second": "0",
            }

        return {
            "trigger": "cron",
            "second": self.second,
            "minute": self.minute,
            "hour": self.hour,
            "day": self.day,
            "month": self.month,
            "day_of_week": self.day_of_week,
        }


@dataclass
class IntervalSchedule:
    """
    Fixed-period schedule with optional jitter

    Examples:

        schedule = interval(minutes=15)
        schedule = interval(hours=1, minutes=30)
        schedule = interval(seconds=30, jitter=5)
    """

    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    jitter: int = 0

    def as_apscheduler_kwargs(self) -> dict[str, Any]:
        return {
            "trigger": "interval",
            "weeks": self.weeks,
            "days": self.days,
            "hours": self.hours,
            "minutes": self.minutes,
            "seconds": self.seconds,
            "jitter": self.jitter,
        }


@dataclass
class OnceAt:
    """
    Fire once at an absolute UTC datetime

    Examples:

        schedule = once_at(datetime(2027, 1, 1, 0, 0))
    """

    run_at: datetime

    def as_apscheduler_kwargs(self) -> dict[str, Any]:
        return {"trigger": "date", "run_date": self.run_at}


class CronKwargs(TypedDict, total=False):
    second: str
    minute: str
    hour: str
    day: str
    month: str
    day_of_week: str


class IntervalKwargs(TypedDict, total=False):
    weeks: int
    days: int
    hours: int
    minutes: int
    seconds: int
    jitter: int


def cron(expr: str | None = None, **kwargs: Unpack[CronKwargs]) -> CronSchedule:
    """
    Create a cron schedule from either a standard cron expression
    """

    return CronSchedule(expr=expr, **kwargs)


def interval(**kwargs: Unpack[IntervalKwargs]) -> IntervalSchedule:
    """
    Create an interval schedule
    """
    return IntervalSchedule(**kwargs)


def once_at(dt: datetime) -> OnceAt:
    """
    Create a one-time schedule for a specific UTC datetime
    """
    return OnceAt(run_at=dt)
