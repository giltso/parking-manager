"""Loading a space's rules and bookings, and asking when it is free.

This is the thin layer between the database and the pure rules in
`app/domain/availability.py`. It knows how rows are stored; it decides nothing.

**Every part of the app asks this one function.** Searching, the owner's week
strip, making a booking, extending one. If a second place ever worked
availability out for itself, the two would drift apart, and the app would offer
a space it then refused to book.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from app.clock import from_text, now_utc, to_text
from app.config import settings
from app.domain.availability import Booking, Rule, Timeline, compute_timeline

# States that still hold a space. Anything else (ended, cancelled, expired) has
# released its time back to the pool and must not block anybody.
ACTIVE_BOOKING_STATES = ("held", "parked")


def _as_date(value: str | None) -> date | None:
    """Turn a stored 'YYYY-MM-DD' into a date, leaving None alone."""
    return date.fromisoformat(value) if value else None


def _as_moment(value: str | None) -> datetime | None:
    """Turn a stored UTC timestamp into a moment, leaving None alone."""
    return from_text(value) if value else None


def load_rules(connection: sqlite3.Connection, space_id: int,
               window_start: datetime, window_end: datetime) -> list[Rule]:
    """Every rule of that space that could touch the window.

    Two shapes need two filters:

    * **One-offs** hold exact moments, so the database can compare them with the
      window directly. An open-ended one ("until I undo it") has no end, and
      counts as long as it started before the window finishes.
    * **Recurring rules** hold local dates, so they are filtered by date with a
      day of slack at each end. A window that starts at 23:00 on Monday
      overlaps a rule valid from Tuesday, once the time zone is taken into
      account, and an opening that runs past midnight belongs to the day before.
      The day of slack costs one extra row and removes a whole class of
      off-by-one bug.

    Deleted rules are left out here, so nothing downstream has to remember.
    """
    first_day = (window_start - timedelta(days=1)).date().isoformat()
    last_day = (window_end + timedelta(days=1)).date().isoformat()

    rows = connection.execute(
        """
        SELECT id, effect, kind, weekdays, start_minute, end_minute,
               valid_from, valid_to, starts_at_utc, ends_at_utc
          FROM rule
         WHERE space_id = ?
           AND deleted_at_utc IS NULL
           AND (
                 (kind = 'oneoff'
                  AND starts_at_utc < ?
                  AND (ends_at_utc IS NULL OR ends_at_utc > ?))
              OR (kind = 'plan'
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR valid_to >= ?))
               )
        """,
        (space_id, to_text(window_end), to_text(window_start), last_day, first_day),
    ).fetchall()

    return [
        Rule(
            id=row["id"],
            effect=row["effect"],
            kind=row["kind"],
            weekdays=row["weekdays"] or 0,
            start_minute=row["start_minute"] or 0,
            end_minute=row["end_minute"] or 0,
            valid_from=_as_date(row["valid_from"]),
            valid_to=_as_date(row["valid_to"]),
            starts_at=_as_moment(row["starts_at_utc"]),
            ends_at=_as_moment(row["ends_at_utc"]),
        )
        for row in rows
    ]


def load_bookings(connection: sqlite3.Connection, space_id: int,
                  window_start: datetime, window_end: datetime,
                  *, ignore_booking_id: int | None = None) -> list[Booking]:
    """Bookings still holding that space during the window.

    Args:
        ignore_booking_id: leave one booking out. Used when a booking is being
            edited or extended, so it doesn't block itself: the question is
            whether the *new* window is free, and its own current time doesn't
            count against it.

    The comparison is "starts before the window ends **and** ends after it
    begins", which is the standard way to test whether two stretches of time
    overlap. Touching end to end is not an overlap, which is why a booking
    ending at 14:00 leaves 14:00 free.
    """
    rows = connection.execute(
        f"""
        SELECT id, start_utc, end_utc
          FROM booking
         WHERE space_id = ?
           AND state IN ({','.join('?' * len(ACTIVE_BOOKING_STATES))})
           AND start_utc < ?
           AND end_utc > ?
           AND (? IS NULL OR id <> ?)
        """,
        (
            space_id, *ACTIVE_BOOKING_STATES,
            to_text(window_end), to_text(window_start),
            ignore_booking_id, ignore_booking_id,
        ),
    ).fetchall()

    return [
        Booking(id=row["id"], start=from_text(row["start_utc"]), end=from_text(row["end_utc"]))
        for row in rows
    ]


def resolve_availability(
    connection: sqlite3.Connection,
    space_id: int,
    window_start: datetime,
    window_end: datetime,
    *,
    now: datetime | None = None,
    ignore_booking_id: int | None = None,
) -> Timeline:
    """When is this space open, taken, or closed, across this window?

    Args:
        connection: an open database connection.
        space_id: which space.
        window_start, window_end: the window to describe, as moments in UTC.
        now: the current moment; defaults to the app's clock. It decides how far
            ahead a recurring opening still counts, so a test can ask "what
            would this look like next Tuesday?".
        ignore_booking_id: see `load_bookings`.

    Returns:
        A `Timeline` covering exactly the window.
    """
    moment = now or now_utc()
    return compute_timeline(
        rules=load_rules(connection, space_id, window_start, window_end),
        bookings=load_bookings(
            connection, space_id, window_start, window_end,
            ignore_booking_id=ignore_booking_id,
        ),
        window_start=window_start,
        window_end=window_end,
        now=moment,
        plan_open_horizon_days=settings.plan_open_horizon_days,
    )
