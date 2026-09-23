"""The database does what we think it does.

These tests exist because the promises in the schema are easy to believe and
easy to get wrong: foreign keys are off by default in SQLite, and a CHECK that
was mistyped accepts everything in silence.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.clock import now_utc, to_text
from app.db import connect, migrate, migration_files


def _add_person(db, name="Dana", unit="7", status="approved"):
    """Insert one person and return the new id. Used by several tests below."""
    cursor = db.execute(
        """INSERT INTO person (name, phone, unit, status, created_at_utc)
           VALUES (?, ?, ?, ?, ?)""",
        (name, "+972500000000", unit, status, to_text(now_utc())),
    )
    return cursor.lastrowid


def test_migrations_create_every_table(db):
    tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "person", "plate", "space", "space_right", "rule", "booking", "event",
        "session", "login_code", "push_subscription", "notification",
        "setting", "schema_version",
    } <= tables


def test_migrating_twice_changes_nothing(tmp_path):
    """Startup runs migrations every time, so repeating them must be harmless."""
    path = str(tmp_path / "twice.db")

    first = connect(path)
    applied_first = migrate(first)
    first.close()

    second = connect(path)
    applied_second = migrate(second)   # same file, second startup
    versions = [row["version"] for row in second.execute("SELECT version FROM schema_version")]
    second.close()

    assert applied_first == [number for number, _ in migration_files()]
    assert applied_second == []        # nothing left to do
    assert versions == applied_first   # and no duplicate rows


def test_foreign_keys_are_enforced(db):
    """A booking must point at a space and a person that exist.

    This fails loudly if `PRAGMA foreign_keys = ON` is ever dropped from
    db.connect(), which would otherwise let orphan rows accumulate unnoticed.
    """
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO booking
                 (space_id, host_person_id, kind, start_utc, end_utc, state, created_at_utc)
               VALUES (999, 999, 'self', ?, ?, 'held', ?)""",
            ("2026-09-23T14:00:00Z", "2026-09-23T16:00:00Z", to_text(now_utc())),
        )


def test_a_booking_cannot_end_before_it_starts(db):
    person_id = _add_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, unit, created_at_utc) VALUES ('12', '7', ?)",
        (to_text(now_utc()),),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO booking
                 (space_id, host_person_id, kind, start_utc, end_utc, state, created_at_utc)
               VALUES (?, ?, 'self', '2026-09-23T16:00:00Z', '2026-09-23T14:00:00Z', 'held', ?)""",
            (space_id, person_id, to_text(now_utc())),
        )


def test_a_guest_booking_must_name_its_guest(db):
    """The label is required before any link exists, so "who is this for?" is
    always answerable (PLAN section 9)."""
    person_id = _add_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, created_at_utc) VALUES ('13', ?)",
        (to_text(now_utc()),),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO booking
                 (space_id, host_person_id, kind, start_utc, end_utc, state, created_at_utc)
               VALUES (?, ?, 'guest', '2026-09-23T14:00:00Z', '2026-09-23T16:00:00Z', 'held', ?)""",
            (space_id, person_id, to_text(now_utc())),
        )


def test_an_unknown_booking_state_is_refused(db):
    """The CHECK list is the last line of defence against a typo in the code."""
    person_id = _add_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, created_at_utc) VALUES ('14', ?)",
        (to_text(now_utc()),),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO booking
                 (space_id, host_person_id, kind, start_utc, end_utc, state, created_at_utc)
               VALUES (?, ?, 'self', '2026-09-23T14:00:00Z', '2026-09-23T16:00:00Z', 'parkd', ?)""",
            (space_id, person_id, to_text(now_utc())),
        )


def test_a_half_filled_rule_is_refused(db):
    """A recurring rule needs weekdays and times; a one-off needs a start moment.

    Mixing them (a 'plan' with a start moment and no weekdays) would resolve to
    nothing at all, so the database refuses it outright.
    """
    person_id = _add_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, created_at_utc) VALUES ('15', ?)",
        (to_text(now_utc()),),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO rule
                 (space_id, effect, kind, starts_at_utc, created_by, created_at_utc)
               VALUES (?, 'open', 'plan', '2026-09-23T14:00:00Z', ?, ?)""",
            (space_id, person_id, to_text(now_utc())),
        )


def test_two_bookings_cannot_share_one_guest_link(db):
    """Guest links are unique, so one fingerprint can never unlock two bookings."""
    person_id = _add_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, created_at_utc) VALUES ('16', ?)",
        (to_text(now_utc()),),
    ).lastrowid

    def book(token_hash):
        db.execute(
            """INSERT INTO booking
                 (space_id, host_person_id, kind, guest_label, guest_token_hash,
                  start_utc, end_utc, state, created_at_utc)
               VALUES (?, ?, 'guest', 'Mum', ?, '2026-09-23T14:00:00Z',
                       '2026-09-23T16:00:00Z', 'held', ?)""",
            (space_id, person_id, token_hash, to_text(now_utc())),
        )

    book("fingerprint-a")
    with pytest.raises(sqlite3.IntegrityError):
        book("fingerprint-a")
