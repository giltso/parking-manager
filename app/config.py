"""Every setting the app has, in one place.

Settings come from environment variables, which are values the operating system
hands to the program when it starts. That is how the same code runs on a laptop
and in a container without editing anything: the container supplies different
values.

Anything a person might want to change without a developer belongs here. If you
find a number written into the middle of the code, it probably belongs here
instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    """Read a whole number from the environment, falling back to `default`.

    Environment variables are always text, so "60" arrives as a string and has
    to be converted. A bad value stops the app at startup with a clear message,
    which is much better than a confusing failure hours later.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from exc


def _text(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


@dataclass(frozen=True)
class Settings:
    """All settings, grouped.

    `frozen=True` makes instances read-only: once the app has started, nothing
    can quietly change a setting underneath the code that already read it.
    """

    # --- where things live --------------------------------------------------
    database_path: str
    base_url: str

    # --- the building -------------------------------------------------------
    tz_name: str            # everything a resident sees is shown in this zone
    default_locale: str     # language for new people and unknown visitors

    # --- booking rules (minutes) -------------------------------------------
    grace_minutes: int      # a held booking expires this long after its start
    margin_minutes: int     # smallest leftover gap best fit may leave behind
    reclaim_notice_minutes: int  # an owner may cancel a booking only while it
                                 # starts more than this far ahead
    expiry_warning_minutes: int  # "about to lose space N" reminder
    end_warning_minutes: int     # "ends soon, extend?" reminder
    extend_step_minutes: int     # how much one tap of [extend] adds
    start_push_skip_minutes: int  # skip "taking it?" for a booking made this
                                  # close to its own start

    # --- how far ahead ------------------------------------------------------
    booking_horizon_days: int      # nothing may be booked beyond this
    plan_open_horizon_days: int    # recurring openings reach only this far
    fit_lookaround_hours: int      # how far around a window we measure free time

    # --- housekeeping -------------------------------------------------------
    tick_seconds: int       # how often the background check runs
    session_days: int       # how long a signed-in phone stays signed in


def load_settings() -> Settings:
    """Build the settings from the environment, with the defaults from PLAN.md."""
    return Settings(
        database_path=_text("DATABASE_PATH", "data/parking.db"),
        base_url=_text("BASE_URL", "http://localhost:8000"),
        tz_name=_text("TZ_NAME", "Asia/Jerusalem"),
        default_locale=_text("DEFAULT_LOCALE", "he"),
        grace_minutes=_int("GRACE_MINUTES", 60),
        margin_minutes=_int("MARGIN_MINUTES", 30),
        reclaim_notice_minutes=_int("RECLAIM_NOTICE_MINUTES", 30),
        expiry_warning_minutes=_int("EXPIRY_WARNING_MINUTES", 10),
        end_warning_minutes=_int("END_WARNING_MINUTES", 15),
        extend_step_minutes=_int("EXTEND_STEP_MINUTES", 60),
        start_push_skip_minutes=_int("START_PUSH_SKIP_MINUTES", 5),
        booking_horizon_days=_int("BOOKING_HORIZON_DAYS", 14),
        plan_open_horizon_days=_int("PLAN_OPEN_HORIZON_DAYS", 7),
        fit_lookaround_hours=_int("FIT_LOOKAROUND_HOURS", 24),
        tick_seconds=_int("TICK_SECONDS", 30),
        session_days=_int("SESSION_DAYS", 180),
    )


# One shared instance. Importing `settings` anywhere gives the same values,
# read once when the app starts.
settings = load_settings()
