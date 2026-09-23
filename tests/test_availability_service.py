"""Tests for loading rules and bookings out of the database.

**Why these tests exist.** `test_availability.py` proves the *rules* are right,
using values typed into the test. This file proves the *loading* is right: that
what the database holds arrives in the shape those rules expect. Those are two
different mistakes. A perfect rule engine fed the wrong rows gives confident
wrong answers, and the queries here are exactly where that happens: a date
compared as text, a booking state left out, a window filter that drops the row
that mattered.

**How they work.** Each test writes real rows into a real (throwaway) database
using the `db` fixture, then asks `resolve_availability` the same questions a
screen would. Nothing is mocked, because the thing under test *is* the meeting
point between SQL and Python.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.clock import now_utc, to_text
from app.domain import timeutil as tu
from app.domain.availability import CLOSED, OPEN
from app.services.availability import (
    load_bookings,
    load_rules,
    resolve_availability,
)

TODAY = date(2026, 9, 22)                                 # a Tuesday
NOW = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)    # 09:00 in the building


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return tu.to_instant(day, hour * 60 + minute)


def make_space(db, label="12") -> int:
    return db.execute(
        "INSERT INTO space (label, unit, created_at_utc) VALUES (?, '7', ?)",
        (label, to_text(now_utc())),
    ).lastrowid


def make_person(db, name="Dana") -> int:
    return db.execute(
        """INSERT INTO person (name, phone, unit, status, created_at_utc)
           VALUES (?, '+972500000000', '7', 'approved', ?)""",
        (name, to_text(now_utc())),
    ).lastrowid


def add_recurring(db, space_id, person_id, effect, weekdays, from_hour, to_hour,
                  valid_from="2026-01-01", valid_to=None, deleted=False):
    """A recurring rule, stored the way the app stores it: local time, as minutes."""
    return db.execute(
        """INSERT INTO rule
             (space_id, effect, kind, weekdays, start_minute, end_minute,
              valid_from, valid_to, created_by, created_at_utc, deleted_at_utc)
           VALUES (?, ?, 'plan', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            space_id, effect, weekdays, from_hour * 60,
            to_hour * 60 if to_hour < 24 else tu.MINUTES_PER_DAY,
            valid_from, valid_to, person_id, to_text(now_utc()),
            to_text(now_utc()) if deleted else None,
        ),
    ).lastrowid


def add_one_off(db, space_id, person_id, effect, start, end):
    """A one-off rule, stored as exact moments."""
    return db.execute(
        """INSERT INTO rule
             (space_id, effect, kind, starts_at_utc, ends_at_utc,
              created_by, created_at_utc)
           VALUES (?, ?, 'oneoff', ?, ?, ?, ?)""",
        (space_id, effect, to_text(start), to_text(end) if end else None,
         person_id, to_text(now_utc())),
    ).lastrowid


def add_booking(db, space_id, person_id, start, end, state="held"):
    return db.execute(
        """INSERT INTO booking
             (space_id, host_person_id, kind, start_utc, end_utc, state, created_at_utc)
           VALUES (?, ?, 'self', ?, ?, ?, ?)""",
        (space_id, person_id, to_text(start), to_text(end), state, to_text(now_utc())),
    ).lastrowid


def state_at(line, moment) -> str:
    for segment in line.segments:
        if segment.start <= moment < segment.end:
            if segment.booking_id is not None:
                return "booked"
            return OPEN if segment.open else CLOSED
    raise AssertionError(f"{moment} is outside the timeline")


# --- the everyday path -------------------------------------------------------

def test_a_stored_recurring_opening_comes_back_as_open_time(db):
    """The ordinary case, end to end: a row in the database becomes open time.

    If this fails, nothing else in the app can work, so it is the first thing to
    check when something looks wrong.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.TUESDAY, 8, 18)

    line = resolve_availability(db, space_id, at(TODAY, 0), at(TODAY, 23), now=NOW)

    assert state_at(line, at(TODAY, 7)) == CLOSED
    assert state_at(line, at(TODAY, 12)) == OPEN
    assert state_at(line, at(TODAY, 19)) == CLOSED


def test_a_removed_rule_no_longer_counts(db):
    """Rules are never deleted, only marked removed, so the query must exclude them.

    This is the mistake that would quietly keep lending a space after its owner
    took the opening away, which is the exact failure the whole design tries to
    avoid.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.ALL_WEEK, 0, 24, deleted=True)

    line = resolve_availability(db, space_id, at(TODAY, 0), at(TODAY, 23), now=NOW)
    assert state_at(line, at(TODAY, 12)) == CLOSED


def test_rules_of_other_spaces_are_ignored(db):
    """Space 12's opening must not open space 13.

    Obvious, and exactly the kind of thing a missing `WHERE space_id = ?` breaks,
    which is why it is worth one short test.
    """
    mine, theirs = make_space(db, "12"), make_space(db, "13")
    person_id = make_person(db)
    add_recurring(db, mine, person_id, OPEN, tu.ALL_WEEK, 0, 24)

    line = resolve_availability(db, theirs, at(TODAY, 0), at(TODAY, 23), now=NOW)
    assert state_at(line, at(TODAY, 12)) == CLOSED


# --- which bookings count ----------------------------------------------------

def test_only_bookings_that_still_hold_the_space_block_it(db):
    """Held and parked block the space. Cancelled, expired and ended do not.

    When a booking expires, its remaining time returns to the pool: that is the
    rule that makes the whole "confirm or lose it" design work. If the query
    counted expired bookings, the space would stay blocked for nothing, and
    nobody would ever see why.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.ALL_WEEK, 0, 24)

    add_booking(db, space_id, person_id, at(TODAY, 10), at(TODAY, 11), state="held")
    add_booking(db, space_id, person_id, at(TODAY, 12), at(TODAY, 13), state="parked")
    add_booking(db, space_id, person_id, at(TODAY, 14), at(TODAY, 15), state="expired")
    add_booking(db, space_id, person_id, at(TODAY, 16), at(TODAY, 17), state="cancelled")
    add_booking(db, space_id, person_id, at(TODAY, 18), at(TODAY, 19), state="ended")

    line = resolve_availability(db, space_id, at(TODAY, 0), at(TODAY, 23), now=NOW)

    assert state_at(line, at(TODAY, 10, 30)) == "booked"
    assert state_at(line, at(TODAY, 12, 30)) == "booked"
    assert state_at(line, at(TODAY, 14, 30)) == OPEN
    assert state_at(line, at(TODAY, 16, 30)) == OPEN
    assert state_at(line, at(TODAY, 18, 30)) == OPEN


def test_a_booking_can_be_told_to_ignore_itself(db):
    """Extending a booking asks "is the new window free?", ignoring the old one.

    Without this, every attempt to extend would collide with the booking doing
    the extending, and the answer would always be no.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.ALL_WEEK, 0, 24)
    booking_id = add_booking(db, space_id, person_id, at(TODAY, 14), at(TODAY, 16))

    blocked = resolve_availability(db, space_id, at(TODAY, 12), at(TODAY, 20), now=NOW)
    assert blocked.is_bookable(at(TODAY, 14), at(TODAY, 18)) is False

    ignoring = resolve_availability(db, space_id, at(TODAY, 12), at(TODAY, 20),
                                    now=NOW, ignore_booking_id=booking_id)
    assert ignoring.is_bookable(at(TODAY, 14), at(TODAY, 18)) is True


# --- the window filters ------------------------------------------------------

def test_a_rule_that_starts_before_the_window_is_still_loaded(db):
    """An overnight opening belongs to the day before, so the filter needs slack.

    The query asks the database for rules by date, and a window in the small
    hours of Wednesday needs Tuesday's rules. This is the bug that would make
    every night-shift opening vanish, and only between midnight and morning,
    which is when nobody is testing.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.TUESDAY, 22, 6)

    tomorrow = TODAY + timedelta(days=1)
    line = resolve_availability(db, space_id, at(tomorrow, 0), at(tomorrow, 8), now=NOW)
    assert state_at(line, at(tomorrow, 2)) == OPEN


def test_rules_and_bookings_far_from_the_window_are_left_in_the_database(db):
    """Loading only what the window needs keeps the work small as history grows.

    Checked on the loaders directly: the timeline would look identical either
    way, so the saving is invisible from outside. After a year of use, most rows
    are old, and a query that fetches them all would slow every screen down.
    """
    space_id, person_id = make_space(db), make_person(db)
    last_year = date(2025, 9, 22)
    add_one_off(db, space_id, person_id, OPEN, at(last_year, 8), at(last_year, 18))
    add_booking(db, space_id, person_id, at(last_year, 9), at(last_year, 10))
    add_recurring(db, space_id, person_id, OPEN, tu.ALL_WEEK, 8, 18)   # current

    rules = load_rules(db, space_id, at(TODAY, 0), at(TODAY, 23))
    bookings = load_bookings(db, space_id, at(TODAY, 0), at(TODAY, 23))

    assert [rule.kind for rule in rules] == ["plan"]
    assert bookings == []


def test_an_open_ended_block_is_loaded_and_keeps_the_space_closed(db):
    """"Blocked until I undo it" has no end date, which SQL comparisons ignore.

    A filter written as `ends_at_utc > window_start` alone would silently drop
    every open-ended block, because a missing value is never greater than
    anything. The space would then open itself.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.ALL_WEEK, 0, 24)
    add_one_off(db, space_id, person_id, CLOSED, at(TODAY, 0), None)

    line = resolve_availability(db, space_id, at(TODAY, 0), at(TODAY, 23), now=NOW)
    assert state_at(line, at(TODAY, 15)) == CLOSED


# --- the horizon, once more, through the database ----------------------------

def test_the_week_horizon_applies_to_stored_rules_too(db):
    """The same "usually away" row is open in three days and closed in ten.

    Proved again here rather than only in the pure tests, because the horizon
    depends on "now" being passed all the way down through the service. A
    default lost along the way would be invisible until an owner complained
    about a booking two weeks out.
    """
    space_id, person_id = make_space(db), make_person(db)
    add_recurring(db, space_id, person_id, OPEN, tu.ALL_WEEK, 0, 24)

    soon = TODAY + timedelta(days=3)
    later = TODAY + timedelta(days=10)

    near = resolve_availability(db, space_id, at(soon, 10), at(soon, 14), now=NOW)
    far = resolve_availability(db, space_id, at(later, 10), at(later, 14), now=NOW)

    assert state_at(near, at(soon, 12)) == OPEN
    assert state_at(far, at(later, 12)) == CLOSED
