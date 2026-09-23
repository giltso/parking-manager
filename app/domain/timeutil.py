"""Turning "every Tuesday, 08:00 to 18:00" into real moments in time.

An owner thinks in the building's clock: "Tuesdays, eight until six". The app
has to answer questions about actual moments: "is the space free between these
two instants?". This file bridges the two.

Most of the year the bridge is dull: Tuesday plus 08:00 is one instant. Twice a
year it isn't, because the clocks change:

* **Spring** (Israel, 2026: 27 March) 02:00 jumps straight to 03:00. Local times
  from 02:00 to 02:59 **do not exist** that day.
* **Autumn** (2026: 25 October) 02:00 falls back to 01:00. Local times from
  01:00 to 01:59 **happen twice**.

An opening set for one of those times is not a mistake by the owner; it is a
mistake to crash, or to silently produce a window running backwards. The rules
here, matching PLAN.md section 3:

* a time that doesn't exist moves forward to the first moment that does;
* a time that happens twice uses the first one.

A recurring rule keeps its wall-clock times through all of this, which is the
whole point: "08:00" means 08:00 on the building's clock in both summer and
winter, even though those are different distances from UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from app.clock import BUILDING_TZ

# Minutes in a day, used often enough to deserve a name.
MINUTES_PER_DAY = 24 * 60

# Which bit of `rule.weekdays` stands for which day. Monday is Python's day 0,
# so the numbers line up with `date.weekday()`.
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = (
    1, 2, 4, 8, 16, 32, 64,
)
ALL_WEEK = MONDAY | TUESDAY | WEDNESDAY | THURSDAY | FRIDAY | SATURDAY | SUNDAY


def weekday_bit(day: date) -> int:
    """The bit standing for that date's weekday, e.g. a Tuesday gives 2."""
    return 1 << day.weekday()


def falls_on(weekdays: int, day: date) -> bool:
    """Does this set of weekdays include that date?

    `weekdays` is a single number holding seven yes/no answers, one bit each.
    Storing seven booleans as one number keeps a rule in one row, and checking
    one is a single `and`.
    """
    return bool(weekdays & weekday_bit(day))


def count_weekdays(weekdays: int) -> int:
    """How many days a week this set covers. Used for measuring how wide a rule is."""
    return bin(weekdays & ALL_WEEK).count("1")


def window_minutes(start_minute: int, end_minute: int) -> int:
    """How long a daily window lasts, in minutes, including windows crossing midnight.

    22:00 to 06:00 is stored as 1320 to 360 and lasts 480 minutes. Midnight to
    midnight is stored as 0 to 1440 and lasts a full day.
    """
    span = end_minute - start_minute
    return span if span > 0 else span + MINUTES_PER_DAY


def local_naive(day: date, minute_of_day: int) -> datetime:
    """A date plus minutes past midnight, with no time zone attached yet."""
    return datetime.combine(day, time(0, 0)) + timedelta(minutes=minute_of_day)


def _exists(wall: datetime) -> bool:
    """Does this wall-clock reading exist on the building's clock?

    The test is a round trip: attach the zone, convert to UTC, convert back. If
    the reading survives unchanged it is real. A time inside the spring gap
    comes back as something else, because that hour never happened.
    """
    attached = wall.replace(tzinfo=BUILDING_TZ)
    round_tripped = attached.astimezone(timezone.utc).astimezone(BUILDING_TZ)
    return round_tripped.replace(tzinfo=None) == wall


def to_instant(day: date, minute_of_day: int) -> datetime:
    """The moment (in UTC) when the building's clock shows this date and time.

    Args:
        day: the local date.
        minute_of_day: minutes past local midnight, 0 to 1440. 1440 means
            midnight at the end of that day, which Python's `time` cannot hold
            and which is why minutes are used rather than clock times.

    Returns:
        A moment in UTC, ready to compare with anything else in the app.

    The two awkward cases:

    * **Doesn't exist** (02:30 on the spring day): step forward a minute at a
      time until the clock reaches a real reading, which lands on 03:00. An
      opening then starts as soon as it possibly can.
    * **Happens twice** (01:30 on the autumn day): `fold=0` picks the first,
      so an opening starts at the earlier of the two and lasts through both.

    The search is capped: a clock change is at most a couple of hours, and a
    loop with no end has no place in code that runs on every screen.
    """
    if minute_of_day > MINUTES_PER_DAY:
        raise ValueError(f"minute_of_day {minute_of_day} is beyond midnight")

    wall = local_naive(day, minute_of_day)

    steps = 0
    while not _exists(wall):
        wall += timedelta(minutes=1)
        steps += 1
        if steps > 240:  # four hours: far more than any real clock change
            raise ValueError(f"no real time near {wall} in {BUILDING_TZ}")

    # fold=0 means "the first time the clock showed this", which matters only on
    # the autumn day, when it shows some readings twice.
    return wall.replace(tzinfo=BUILDING_TZ, fold=0).astimezone(timezone.utc)


def local_date_of(moment: datetime) -> date:
    """Which local date a moment falls on, for the building."""
    return moment.astimezone(BUILDING_TZ).date()


def local_dates_touching(start: datetime, end: datetime) -> list[date]:
    """Every local date a window touches, plus the day before.

    The extra day matters for windows that cross midnight: an opening from
    22:00 Monday to 06:00 Tuesday belongs to Monday, so a question about
    Tuesday morning has to look at Monday's rules too.
    """
    first = local_date_of(start) - timedelta(days=1)
    last = local_date_of(end)
    span = (last - first).days
    return [first + timedelta(days=offset) for offset in range(span + 1)]


@dataclass(frozen=True)
class Occurrence:
    """One concrete stretch of time produced by a rule.

    A recurring rule produces one of these per matching day; a one-off produces
    exactly one. From here on, nothing needs to know which kind it came from.
    """

    start: datetime          # in UTC
    end: datetime            # in UTC
    effect: str              # 'open' or 'closed'
    kind: str                # 'plan' or 'oneoff', which decides the first tie
    rule_id: int | None
    coverage_minutes: float  # how much time the whole rule covers, ever
    weekly_minutes: float    # how much it covers in an average week


def clip(occurrence_start: datetime, occurrence_end: datetime,
         window_start: datetime, window_end: datetime) -> tuple[datetime, datetime] | None:
    """Trim a stretch to the window being asked about, or None if it misses.

    Every screen asks about a window (today, this week). Trimming here means
    later code never handles a rule stretching off into last year.
    """
    start = max(occurrence_start, window_start)
    end = min(occurrence_end, window_end)
    return (start, end) if start < end else None
