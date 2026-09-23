"""The only place the app asks what time it is.

Why bother, when Python can tell the time anywhere? Because half of this app is
about time: a booking expires 60 minutes after it starts, an owner may cancel
only while a booking is more than 30 minutes away. If every file called the
system clock directly, testing those rules would mean waiting an hour.

With one source of time, a test can say "pretend it is 14:05" and every part of
the app agrees. Nothing else in the app may call `datetime.now()`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings

# A timestamp exactly as it is stored in the database: UTC, to the second, with
# a "Z" on the end meaning "this is UTC". Fixed width, so comparing two of them
# as plain text gives the same answer as comparing two moments in time.
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# The building's own zone. Residents think in this; the database never uses it.
BUILDING_TZ = ZoneInfo(settings.tz_name)

# When this is set, it is the current time. Tests set it; the app never does.
_frozen_now: datetime | None = None


def now_utc() -> datetime:
    """The current moment, in UTC, accurate to the second.

    Seconds are enough here (nothing in parking cares about milliseconds), and
    dropping the fraction means the value written to the database and the value
    in memory are exactly the same.
    """
    if _frozen_now is not None:
        return _frozen_now
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_text(moment: datetime) -> str:
    """Turn a moment into the text the database stores.

    A moment without a time zone is rejected rather than guessed: "14:00" is
    meaningless until you know 14:00 where.
    """
    if moment.tzinfo is None:
        raise ValueError("moment has no time zone; refusing to guess")
    return moment.astimezone(timezone.utc).strftime(UTC_FORMAT)


def from_text(text: str) -> datetime:
    """Turn stored text back into a moment in UTC."""
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=timezone.utc)


def to_building_time(moment: datetime) -> datetime:
    """The same moment, expressed on the building's clock, for display only."""
    return moment.astimezone(BUILDING_TZ)


def freeze(moment: datetime) -> None:
    """Pin the clock (tests only). `moment` must carry a time zone."""
    global _frozen_now
    if moment.tzinfo is None:
        raise ValueError("freeze needs a moment with a time zone")
    _frozen_now = moment.astimezone(timezone.utc).replace(microsecond=0)


def advance(**shift: float) -> None:
    """Move a frozen clock forward, e.g. `advance(minutes=61)` (tests only)."""
    global _frozen_now
    if _frozen_now is None:
        raise RuntimeError("advance() needs freeze() first")
    _frozen_now = _frozen_now + timedelta(**shift)


def unfreeze() -> None:
    """Hand the clock back to the real world (tests only)."""
    global _frozen_now
    _frozen_now = None
