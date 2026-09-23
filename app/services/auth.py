"""Signing in, and working out who is asking.

There are no passwords anywhere in this app. Residents sign up through a link
shared in the building's group chat, stay signed in on their phone for months,
and move to a new phone with a short code. Anyone who loses a phone gets a
one-time link from a coordinator.

Passwords were skipped on purpose: resetting one needs email or SMS, which this
app deliberately doesn't have, and a forgotten password would mean a neighbour
can't park.

Three secrets exist here, and all three follow the same rule: **only a
fingerprint is stored**. A fingerprint (a hash) is a one-way summary. The app
can check whether a code matches one, but nobody holding a copy of the database
can work out the code. It is the same reason a well-built site never stores your
password.

| Secret | Lives in | Lasts |
|---|---|---|
| Session token | a cookie on the phone | months, extended by use |
| Device code | shown on a signed-in phone | 10 minutes, one use |
| Sign-in link | sent by a coordinator | 7 days, one use |
"""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.clock import from_text, now_utc, to_text
from app.config import settings
from app.permissions import Actor
from app.services import events

# Characters a person can read off a screen and type without mistakes: no 0/O,
# no 1/I/L. A code is meant to be read aloud across a room.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8

DEVICE_CODE_MINUTES = 10      # long enough to walk to the other phone
SIGNIN_LINK_DAYS = 7          # a coordinator may send it before it is needed

JOIN_CODE_KEY = "join_code"   # the row in `setting` holding the sign-up code


# --- fingerprints ------------------------------------------------------------

def fingerprint(secret: str) -> str:
    """The one-way summary of a secret, which is all the database ever holds."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _new_secret(length: int = 32) -> str:
    """A long random string, safe to use as a token.

    `secrets` is the random generator made for this. The everyday `random`
    module is predictable if you see enough of its output, which is fine for
    shuffling a list and not for anything that guards a door.
    """
    return secrets.token_urlsafe(length)


def _new_code() -> str:
    """A short code a person will type, from the readable alphabet."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(typed: str) -> str:
    """Let people type a code however they like.

    Spaces, dashes and lower case all become the stored form, so "k7m4-qp x2"
    works. Codes are hard enough to type on a phone in a car park.
    """
    return re.sub(r"[^A-Za-z0-9]", "", typed).upper()


# --- phone numbers -----------------------------------------------------------

def normalise_phone(typed: str) -> str:
    """Store every phone number one way, so one person can't appear twice.

    `050-123-4567`, `0501234567` and `+972 50 123 4567` are the same number.
    Israeli local numbers start with 0, which stands for the country code.

    Returns the number as `+972…`. Raises ValueError if it cannot be read,
    because a number nobody can call is worse than being asked to type it again.
    """
    digits = re.sub(r"[^\d+]", "", typed or "")

    if digits.startswith("+"):
        cleaned = "+" + re.sub(r"\D", "", digits[1:])
    elif digits.startswith("972"):
        cleaned = "+" + digits
    elif digits.startswith("0"):
        cleaned = "+972" + digits[1:]
    else:
        cleaned = digits

    if not re.fullmatch(r"\+\d{9,15}", cleaned):
        raise ValueError(f"that doesn't look like a phone number: {typed!r}")
    return cleaned


# --- the building's sign-up code ---------------------------------------------

def join_code(connection: sqlite3.Connection) -> str | None:
    """The current sign-up code, or None if nobody has made one yet."""
    row = connection.execute(
        "SELECT value FROM setting WHERE key = ?", (JOIN_CODE_KEY,)
    ).fetchone()
    return row["value"] if row else None


def rotate_join_code(connection: sqlite3.Connection, *, by_person_id: int | None,
                     actor_kind: str = "coordinator") -> str:
    """Make a new sign-up code, retiring the old one. Returns the new code.

    Used when the link has spread further than intended. Anyone already signed
    in stays signed in: this only affects new sign-ups.
    """
    code = _new_secret(16)
    connection.execute(
        """INSERT INTO setting (key, value, updated_at_utc) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at_utc = excluded.updated_at_utc""",
        (JOIN_CODE_KEY, code, to_text(now_utc())),
    )
    events.record(connection, "join_code.rotated",
                  actor_kind=actor_kind, actor_person_id=by_person_id)
    return code


# --- people ------------------------------------------------------------------

@dataclass(frozen=True)
class Person:
    """A resident, as the app needs them day to day."""

    id: int
    name: str
    phone: str
    unit: str
    locale: str
    status: str
    is_coordinator: bool


def _person_from_row(row: sqlite3.Row) -> Person:
    return Person(
        id=row["id"],
        name=row["name"],
        phone=row["phone"],
        unit=row["unit"],
        locale=row["locale"],
        status=row["status"],
        is_coordinator=bool(row["is_coordinator"]),
    )


def get_person(connection: sqlite3.Connection, person_id: int) -> Person | None:
    row = connection.execute(
        "SELECT * FROM person WHERE id = ?", (person_id,)
    ).fetchone()
    return _person_from_row(row) if row else None


def sign_up(connection: sqlite3.Connection, *, name: str, phone: str, unit: str,
            locale: str) -> Person:
    """Create an account, waiting for a coordinator to approve it.

    The account can look around straight away, which makes the wait make sense,
    but it cannot book or hold a space until approved. That approval is what
    keeps the building's list to the building, even when the sign-up link is
    forwarded to someone's cousin.
    """
    name = (name or "").strip()
    unit = (unit or "").strip()
    if not name:
        raise ValueError("a name is needed")
    if not unit:
        raise ValueError("an apartment number is needed")

    cursor = connection.execute(
        """INSERT INTO person (name, phone, unit, locale, status, created_at_utc)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (name, normalise_phone(phone), unit,
         locale if locale in ("he", "en") else settings.default_locale,
         to_text(now_utc())),
    )
    person = get_person(connection, cursor.lastrowid)
    events.record(connection, "person.joined", actor_person_id=person.id,
                  unit=person.unit)
    return person


def set_status(connection: sqlite3.Connection, person_id: int, status: str, *,
               by_person_id: int) -> None:
    """Approve, reject or deactivate an account. Only coordinators reach this.

    Rejection and deactivation also end every session that account has, so
    access stops at once rather than whenever the cookie happens to expire.
    """
    if status not in ("pending", "approved", "rejected", "deactivated"):
        raise ValueError(f"unknown status: {status}")

    connection.execute("UPDATE person SET status = ? WHERE id = ?", (status, person_id))
    if status in ("rejected", "deactivated"):
        connection.execute("DELETE FROM session WHERE person_id = ?", (person_id,))

    events.record(connection, f"person.{status}", actor_kind="coordinator",
                  actor_person_id=by_person_id, subject_person_id=person_id)


def update_profile(connection: sqlite3.Connection, person_id: int, *, name: str,
                   phone: str, unit: str, locale: str) -> None:
    """Change the details a resident owns: their name, phone, apartment, language."""
    connection.execute(
        """UPDATE person SET name = ?, phone = ?, unit = ?, locale = ? WHERE id = ?""",
        ((name or "").strip(), normalise_phone(phone), (unit or "").strip(),
         locale if locale in ("he", "en") else settings.default_locale, person_id),
    )
    events.record(connection, "person.updated", actor_person_id=person_id)


# --- sessions ----------------------------------------------------------------

def start_session(connection: sqlite3.Connection, person_id: int, *,
                  user_agent: str | None = None) -> str:
    """Sign a phone in. Returns the token to put in the cookie.

    The token is returned once and never stored: the database keeps only its
    fingerprint. So this value exists in exactly two places, the cookie and this
    moment, which is what makes a leaked database useless for signing in.
    """
    token = _new_secret()
    moment = now_utc()
    connection.execute(
        """INSERT INTO session
             (token_hash, person_id, expires_at_utc, last_seen_at_utc,
              user_agent, created_at_utc)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            fingerprint(token),
            person_id,
            to_text(moment + timedelta(days=settings.session_days)),
            to_text(moment),
            (user_agent or "")[:200],     # enough to recognise a device
            to_text(moment),
        ),
    )
    events.record(connection, "session.started", actor_person_id=person_id)
    return token


def person_for_session(connection: sqlite3.Connection, token: str | None, *,
                       now: datetime | None = None) -> Person | None:
    """Who does this cookie belong to? None if it is unknown or out of date.

    A session that is still in use is extended, so a resident who opens the app
    every week is never signed out, while a forgotten phone eventually is.
    """
    if not token:
        return None
    moment = now or now_utc()

    row = connection.execute(
        """SELECT person.*, session.id AS session_id, session.expires_at_utc
             FROM session JOIN person ON person.id = session.person_id
            WHERE session.token_hash = ?""",
        (fingerprint(token),),
    ).fetchone()

    if row is None:
        return None
    if from_text(row["expires_at_utc"]) <= moment:
        return None
    if row["status"] in ("rejected", "deactivated"):
        return None

    connection.execute(
        "UPDATE session SET last_seen_at_utc = ?, expires_at_utc = ? WHERE id = ?",
        (to_text(moment),
         to_text(moment + timedelta(days=settings.session_days)),
         row["session_id"]),
    )
    return _person_from_row(row)


def end_session(connection: sqlite3.Connection, token: str) -> None:
    """Sign this phone out."""
    connection.execute("DELETE FROM session WHERE token_hash = ?", (fingerprint(token),))


def end_other_session(connection: sqlite3.Connection, session_id: int,
                      person_id: int) -> None:
    """Sign one of your own devices out, from another one.

    `person_id` is part of the query rather than checked beforehand, so a
    request naming somebody else's session simply deletes nothing.
    """
    connection.execute(
        "DELETE FROM session WHERE id = ? AND person_id = ?", (session_id, person_id)
    )
    events.record(connection, "session.ended", actor_person_id=person_id)


def sessions_of(connection: sqlite3.Connection, person_id: int) -> list[sqlite3.Row]:
    """The devices this person is signed in on, most recently used first."""
    return connection.execute(
        """SELECT id, user_agent, last_seen_at_utc, created_at_utc
             FROM session WHERE person_id = ?
            ORDER BY last_seen_at_utc DESC""",
        (person_id,),
    ).fetchall()


# --- one-time codes ----------------------------------------------------------

def issue_code(connection: sqlite3.Connection, person_id: int, *, purpose: str,
               by_person_id: int | None = None,
               actor_kind: str = "person") -> str:
    """Make a one-time code for signing in. Returns it once; only its fingerprint is kept.

    Two purposes:

    * `device`: shown on a phone that is already signed in, to add another one.
      Short-lived, because the person is standing right there.
    * `invite`: issued by a coordinator for someone who lost their phone. It
      lasts a week, because it may be sent before it is needed.
    """
    if purpose not in ("device", "invite"):
        raise ValueError(f"unknown purpose: {purpose}")

    code = _new_code()
    lifetime = (timedelta(minutes=DEVICE_CODE_MINUTES) if purpose == "device"
                else timedelta(days=SIGNIN_LINK_DAYS))

    connection.execute(
        """INSERT INTO login_code
             (code_hash, person_id, purpose, expires_at_utc, created_at_utc)
           VALUES (?, ?, ?, ?, ?)""",
        (fingerprint(code), person_id, purpose,
         to_text(now_utc() + lifetime), to_text(now_utc())),
    )
    events.record(connection, "code.issued", actor_kind=actor_kind,
                  actor_person_id=by_person_id or person_id,
                  subject_person_id=person_id, purpose=purpose)
    return code


def peek_code(connection: sqlite3.Connection, code: str, *,
              now: datetime | None = None) -> Person | None:
    """Who would this code sign in, without using it up?

    The sign-in link shows "Sign in as Dana?" before anything happens. That
    matters because messaging apps fetch links to build a preview: if merely
    opening the link signed you in, a preview would burn the code before the
    person ever tapped it.
    """
    moment = now or now_utc()
    row = connection.execute(
        """SELECT person.*, login_code.expires_at_utc, login_code.used_at_utc
             FROM login_code JOIN person ON person.id = login_code.person_id
            WHERE login_code.code_hash = ?""",
        (fingerprint(normalise_code(code)),),
    ).fetchone()

    if row is None or row["used_at_utc"] is not None:
        return None
    if from_text(row["expires_at_utc"]) <= moment:
        return None
    if row["status"] in ("rejected", "deactivated"):
        return None
    return _person_from_row(row)


def use_code(connection: sqlite3.Connection, code: str, *,
             user_agent: str | None = None,
             now: datetime | None = None) -> tuple[Person, str] | None:
    """Spend a code and sign in. Returns (person, session token), or None.

    One use only: the code is marked spent in the same breath as the session is
    created, so a code shared in a group chat cannot be used twice.

    A code that is found but unusable (expired, already spent) has its attempt
    count raised, which is what a coordinator looks at when someone says the
    link "doesn't work".
    """
    moment = now or now_utc()
    cleaned = normalise_code(code)
    row = connection.execute(
        "SELECT * FROM login_code WHERE code_hash = ?", (fingerprint(cleaned),)
    ).fetchone()

    if row is None:
        return None

    unusable = (
        row["used_at_utc"] is not None
        or from_text(row["expires_at_utc"]) <= moment
    )
    if unusable:
        connection.execute(
            "UPDATE login_code SET attempts = attempts + 1 WHERE id = ?", (row["id"],)
        )
        return None

    person = get_person(connection, row["person_id"])
    if person is None or person.status in ("rejected", "deactivated"):
        return None

    connection.execute(
        "UPDATE login_code SET used_at_utc = ? WHERE id = ?", (to_text(moment), row["id"])
    )
    token = start_session(connection, person.id, user_agent=user_agent)
    events.record(connection, "code.used", actor_person_id=person.id,
                  purpose=row["purpose"])
    return person, token


# --- who is asking -----------------------------------------------------------

def actor_for(connection: sqlite3.Connection, person: Person | None, *,
              now: datetime | None = None) -> Actor:
    """Turn a person into the `Actor` every permission check expects.

    The work here is collecting the space rights that are live **right now**.
    A manager's stand-in ends on a date; once it has passed, the right is simply
    absent, so no permission rule has to think about expiry.
    """
    if person is None:
        return Actor()

    moment = to_text(now or now_utc())
    rows = connection.execute(
        """SELECT space_id, role FROM space_right
            WHERE person_id = ?
              AND status = 'active'
              AND valid_from_utc <= ?
              AND (valid_to_utc IS NULL OR valid_to_utc > ?)""",
        (person.id, moment, moment),
    ).fetchall()

    roles: dict[int, set[str]] = {}
    for row in rows:
        roles.setdefault(row["space_id"], set()).add(row["role"])

    return Actor(
        person_id=person.id,
        status=person.status,
        is_coordinator=person.is_coordinator,
        space_roles=roles,
    )
