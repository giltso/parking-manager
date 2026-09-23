"""Tests for turning "Tuesday, 08:00" into a real moment.

**Why these tests exist.** This file is where the clock changes twice a year and
where windows cross midnight. Both are rare, both are impossible to notice by
using the app in March, and both would show up as an opening at the wrong hour,
which nobody would report as a bug: they would just think the app is unreliable.

**How they work.** No database, no app, no waiting: each test builds a date and
a minute, asks for the moment, and checks what the building's clock would show.
Comparisons are made in local time, because that is how the mistake would be
noticed by a resident.

The clock-change dates below are the real ones for Israel, read from the
system's time-zone data:

* 27 March 2026: 02:00 jumps to 03:00, so 02:00-02:59 never happens.
* 25 October 2026: 02:00 falls back to 01:00, so 01:00-01:59 happens twice.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.clock import BUILDING_TZ
from app.domain import timeutil as tu

SPRING_FORWARD = date(2026, 3, 27)   # the day an hour disappears
FALL_BACK = date(2026, 10, 25)       # the day an hour repeats
ORDINARY_DAY = date(2026, 9, 22)     # a Tuesday, nothing special about it


def local(moment: datetime) -> datetime:
    """The same moment on the building's clock, which is how residents read it."""
    return moment.astimezone(BUILDING_TZ)


# --- the ordinary case, so the awkward ones have something to differ from ----

def test_a_normal_morning_is_just_that_morning():
    """The dull case is worth pinning: if this breaks, everything else is noise."""
    moment = tu.to_instant(ORDINARY_DAY, 8 * 60)     # 08:00
    assert local(moment).hour == 8
    assert local(moment).date() == ORDINARY_DAY
    assert moment.tzinfo == timezone.utc             # stored times are always UTC


def test_midnight_at_the_end_of_a_day_is_the_next_midnight():
    """1440 means "the end of this day", which Python's time type cannot express.

    Storing minutes rather than clock times is what makes an all-day opening
    (00:00 to 1440) possible at all, so this checks the far edge behaves.
    """
    moment = tu.to_instant(ORDINARY_DAY, tu.MINUTES_PER_DAY)
    assert local(moment).date() == ORDINARY_DAY + timedelta(days=1)
    assert local(moment).hour == 0


# --- the hour that doesn't exist --------------------------------------------

def test_a_time_inside_the_spring_gap_moves_to_when_the_clock_restarts():
    """02:30 on the spring day never happens. The opening starts at 03:00 instead.

    Why it matters: an owner with a night-shift schedule has a rule at 02:30
    twice a year. Without this, the app would either crash or invent a moment.
    Moving forward means the opening begins as soon as it can, which is what an
    owner offering their space would want.
    """
    moment = tu.to_instant(SPRING_FORWARD, 2 * 60 + 30)
    shown = local(moment)
    assert (shown.hour, shown.minute) == (3, 0)
    assert shown.date() == SPRING_FORWARD


def test_times_either_side_of_the_gap_are_untouched():
    """Only the missing hour is adjusted; the rest of that day is normal.

    A fix that quietly shifted the whole day would pass the test above and be
    wrong, so this is the test that keeps the first one honest.
    """
    before = local(tu.to_instant(SPRING_FORWARD, 1 * 60 + 30))
    after = local(tu.to_instant(SPRING_FORWARD, 4 * 60))
    assert (before.hour, before.minute) == (1, 30)
    assert (after.hour, after.minute) == (4, 0)


def test_a_window_across_the_spring_gap_is_an_hour_shorter_in_real_time():
    """08:00-18:00 stays 08:00-18:00 on the clock, which is nine real hours here.

    This is the point of storing recurring rules as wall-clock times: the owner
    said "until six", and it ends at six, even though that day is short. The
    test measures real elapsed time to prove the difference is deliberate.
    """
    start = tu.to_instant(SPRING_FORWARD, 8 * 60)
    end = tu.to_instant(SPRING_FORWARD, 18 * 60)
    assert local(start).hour == 8 and local(end).hour == 18
    assert (end - start) == timedelta(hours=10)      # the gap is before 08:00

    # A window that straddles the gap itself is the short one.
    early_start = tu.to_instant(SPRING_FORWARD, 0)
    assert (tu.to_instant(SPRING_FORWARD, 8 * 60) - early_start) == timedelta(hours=7)


# --- the hour that happens twice --------------------------------------------

def test_a_time_that_happens_twice_uses_the_first_one():
    """01:30 occurs twice on the autumn day. We take the earlier.

    Taking the earlier means an opening covers both passes through that hour
    rather than starting in the middle of the repeat, so a space offered "from
    01:30" really is available from the first 01:30.
    """
    moment = tu.to_instant(FALL_BACK, 1 * 60 + 30)
    shown = local(moment)
    assert (shown.hour, shown.minute) == (1, 30)
    # The earlier pass is still on summer time, three hours ahead of UTC.
    assert shown.utcoffset() == timedelta(hours=3)


def test_a_full_day_in_autumn_really_is_twenty_five_hours():
    """Midnight to midnight on the fall-back day is 25 hours of real time.

    An all-day opening must cover the whole day, repeated hour included. If the
    code assumed every day is 24 hours, the last hour would silently close.
    """
    start = tu.to_instant(FALL_BACK, 0)
    end = tu.to_instant(FALL_BACK, tu.MINUTES_PER_DAY)
    assert (end - start) == timedelta(hours=25)


def test_a_full_day_in_spring_really_is_twenty_three_hours():
    """The mirror image: the short day. Both directions have to work."""
    start = tu.to_instant(SPRING_FORWARD, 0)
    end = tu.to_instant(SPRING_FORWARD, tu.MINUTES_PER_DAY)
    assert (end - start) == timedelta(hours=23)


# --- weekdays and window lengths --------------------------------------------

def test_weekday_bits_match_the_calendar():
    """Seven days are stored as seven bits of one number, so a rule is one row.

    The risk with bit tricks is an off-by-one that puts Tuesday's opening on
    Wednesday, which is why this checks against real dates rather than the
    constants' own arithmetic.
    """
    monday, tuesday, sunday = date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 27)
    assert tu.falls_on(tu.TUESDAY, tuesday)
    assert not tu.falls_on(tu.TUESDAY, monday)
    assert tu.falls_on(tu.SUNDAY, sunday)
    assert tu.falls_on(tu.ALL_WEEK, monday)
    assert tu.count_weekdays(tu.ALL_WEEK) == 7
    assert tu.count_weekdays(tu.MONDAY | tu.FRIDAY) == 2


@pytest.mark.parametrize(
    "start_minute, end_minute, expected_minutes, description",
    [
        (8 * 60, 18 * 60, 600, "an ordinary daytime window"),
        (0, tu.MINUTES_PER_DAY, 1440, "all day"),
        (22 * 60, 6 * 60, 480, "overnight, crossing midnight"),
        (23 * 60 + 30, 0, 30, "half an hour up to midnight"),
    ],
)
def test_window_length(start_minute, end_minute, expected_minutes, description):
    """How long a daily window lasts, including the ones that cross midnight.

    Written as a table because the cases differ only in numbers. A night-shift
    opening (22:00 to 06:00) is stored with an end *smaller* than its start, and
    subtracting those the obvious way gives a negative length.
    """
    assert tu.window_minutes(start_minute, end_minute) == expected_minutes, description


def test_dates_touching_a_window_include_the_day_before():
    """A question about Tuesday must also look at Monday's rules.

    An opening from 22:00 Monday to 06:00 Tuesday belongs to Monday. Without the
    extra day, a resident asking about Tuesday at 01:00 would be told the space
    is closed while it is in fact open.
    """
    window_start = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
    days = tu.local_dates_touching(window_start, window_end)
    assert date(2026, 9, 21) in days
    assert date(2026, 9, 22) in days


def test_clipping_keeps_only_the_overlap():
    """Rules are trimmed to the window, so later code never sees last year.

    The third case is the important one: touching end-to-end is not an overlap,
    or a booking ending at 14:00 would block one starting at 14:00.
    """
    window = (datetime(2026, 9, 22, 10, tzinfo=timezone.utc),
              datetime(2026, 9, 22, 14, tzinfo=timezone.utc))

    inside = tu.clip(datetime(2026, 9, 22, 11, tzinfo=timezone.utc),
                     datetime(2026, 9, 22, 12, tzinfo=timezone.utc), *window)
    assert inside == (datetime(2026, 9, 22, 11, tzinfo=timezone.utc),
                      datetime(2026, 9, 22, 12, tzinfo=timezone.utc))

    overlapping = tu.clip(datetime(2026, 9, 22, 9, tzinfo=timezone.utc),
                          datetime(2026, 9, 22, 11, tzinfo=timezone.utc), *window)
    assert overlapping[0] == window[0]        # trimmed to the window's start

    touching = tu.clip(datetime(2026, 9, 22, 8, tzinfo=timezone.utc),
                       datetime(2026, 9, 22, 10, tzinfo=timezone.utc), *window)
    assert touching is None
