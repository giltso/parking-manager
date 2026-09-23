"""Tests for signing in, and for working out who is asking.

**Why these tests exist.** This is the door to the building. A mistake here is
not a wrong parking space: it is a stranger holding a resident's account, or a
resident locked out with no way back in. None of it is visible from the screens,
because a broken check looks exactly like a working one until someone tries.

**What they cover.**

1. secrets are stored as fingerprints only, never as themselves;
2. codes work once, expire, and say nothing useful when wrong;
3. sessions end when they should, including when an account is turned off;
4. a new account can look but not act, until a coordinator approves it;
5. the `Actor` handed to the permission rules matches reality, especially when a
   stand-in's right has run out.

**How they work.** Against a real throwaway database, through the service
functions the screens use, with the clock supplied by the test where the answer
depends on time.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.clock import now_utc, to_text
from app.permissions import BOOK, VIEW_SPACES, can
from app.services import auth


def a_person(db, name="Dana", phone="050-123-4567", unit="7", status="approved"):
    person = auth.sign_up(db, name=name, phone=phone, unit=unit, locale="he")
    if status != "pending":
        db.execute("UPDATE person SET status = ? WHERE id = ?", (status, person.id))
    return auth.get_person(db, person.id)


# --- phone numbers -----------------------------------------------------------

@pytest.mark.parametrize(
    "typed, stored",
    [
        ("0501234567", "+972501234567"),
        ("050-123-4567", "+972501234567"),
        ("+972 50 123 4567", "+972501234567"),
        ("972501234567", "+972501234567"),
    ],
)
def test_the_same_number_typed_differently_is_stored_once(typed, stored):
    """Four ways of writing one number must become one number.

    Why it matters: the phone number is how neighbours reach each other when
    something goes wrong, and how a coordinator recognises a person. Two
    spellings would mean the same resident appearing twice in the list, with one
    of the entries holding their space.
    """
    assert auth.normalise_phone(typed) == stored


@pytest.mark.parametrize("nonsense", ["", "hello", "12", "+"])
def test_something_that_is_not_a_phone_number_is_refused(nonsense):
    """Refusing beats storing something nobody can call.

    The resident is asked to type it again, which is a small annoyance now
    instead of an unreachable neighbour later.
    """
    with pytest.raises(ValueError):
        auth.normalise_phone(nonsense)


# --- what the database actually holds ----------------------------------------

def test_the_session_token_itself_is_never_stored(db):
    """A copy of the database must not let anyone sign in as a resident.

    This is the test that would catch the classic mistake of storing the token
    "so we can look it up". The check searches the whole session table for the
    token's text: it must appear nowhere.
    """
    person = a_person(db)
    token = auth.start_session(db, person.id)

    stored = [dict(row) for row in db.execute("SELECT * FROM session").fetchall()]
    assert token not in str(stored)
    assert stored[0]["token_hash"] == auth.fingerprint(token)


def test_the_code_itself_is_never_stored(db):
    """Same rule for the short codes people type. Same reason."""
    person = a_person(db)
    code = auth.issue_code(db, person.id, purpose="device")

    stored = [dict(row) for row in db.execute("SELECT * FROM login_code").fetchall()]
    assert code not in str(stored)


def test_codes_avoid_characters_people_misread():
    """Codes are read off one screen and typed into another, often in a car park.

    Zero and capital O, one and capital I, are the pairs that cause a wrong
    code and a phone call. Leaving them out costs a little entropy and saves
    that call.
    """
    assert set("O01IL") & set(auth.CODE_ALPHABET) == set()


# --- codes work once ---------------------------------------------------------

def test_a_code_signs_you_in_and_then_stops_working(db):
    """One use only, so a code shared in a group chat can't be used twice.

    The second attempt returns nothing rather than an error, which is also what
    a stranger guessing would see.
    """
    person = a_person(db)
    code = auth.issue_code(db, person.id, purpose="device")

    first = auth.use_code(db, code)
    assert first is not None and first[0].id == person.id

    assert auth.use_code(db, code) is None


def test_an_expired_code_does_not_work(db):
    """Device codes last ten minutes, so a screenshot from yesterday is useless.

    The clock is supplied by the test rather than waited for, which is the whole
    reason the app has one source of time.
    """
    person = a_person(db)
    code = auth.issue_code(db, person.id, purpose="device")

    later = now_utc() + timedelta(minutes=auth.DEVICE_CODE_MINUTES + 1)
    assert auth.use_code(db, code, now=later) is None


def test_a_code_can_be_typed_however_people_type_it(db):
    """Spaces, dashes and lower case all work: the code is the letters.

    Someone reading a code aloud across a room will not reproduce the spacing,
    and being told "wrong code" for that reason is infuriating.
    """
    person = a_person(db)
    code = auth.issue_code(db, person.id, purpose="device")
    scrambled = f" {code[:4].lower()}-{code[4:].lower()} "

    assert auth.use_code(db, scrambled) is not None


def test_looking_at_a_sign_in_link_does_not_spend_it(db):
    """Opening a link only shows "Sign in as Dana?"; the button spends it.

    Messaging apps fetch links to build previews. If opening the link signed
    someone in, WhatsApp would burn the code before the person ever tapped it,
    and every lost-phone rescue would fail.
    """
    person = a_person(db)
    code = auth.issue_code(db, person.id, purpose="invite")

    assert auth.peek_code(db, code).id == person.id
    assert auth.peek_code(db, code).id == person.id      # still unspent
    assert auth.use_code(db, code) is not None           # and still usable


def test_an_unusable_code_is_counted(db):
    """Attempts on a known-but-dead code are recorded, for when someone reports it.

    It answers the coordinator's question: did the link arrive and fail, or was
    it never opened?
    """
    person = a_person(db)
    code = auth.issue_code(db, person.id, purpose="device")
    auth.use_code(db, code)
    auth.use_code(db, code)          # a second try on a spent code

    attempts = db.execute("SELECT attempts FROM login_code").fetchone()["attempts"]
    assert attempts == 1


# --- sessions ----------------------------------------------------------------

def test_a_made_up_cookie_signs_nobody_in(db):
    """Guessing a session token must be pointless, not merely unlikely."""
    a_person(db)
    assert auth.person_for_session(db, "not-a-real-token") is None
    assert auth.person_for_session(db, None) is None


def test_a_session_in_regular_use_keeps_going(db):
    """A resident who opens the app now and then is never signed out.

    The opposite (a fixed expiry) would sign people out mid-year for no reason
    they could understand.
    """
    person = a_person(db)
    token = auth.start_session(db, person.id)

    much_later = now_utc() + timedelta(days=100)
    assert auth.person_for_session(db, token, now=much_later) is not None

    # That visit pushed the expiry out again, so a later one still works.
    later_still = much_later + timedelta(days=100)
    assert auth.person_for_session(db, token, now=later_still) is not None


def test_a_forgotten_session_eventually_expires(db):
    """A phone that is never used again stops being a way in."""
    person = a_person(db)
    token = auth.start_session(db, person.id)

    from app.config import settings
    beyond = now_utc() + timedelta(days=settings.session_days + 1)
    assert auth.person_for_session(db, token, now=beyond) is None


def test_deactivating_an_account_signs_out_every_device(db):
    """Access stops at once, not whenever a cookie happens to run out.

    This is what a coordinator expects when they deactivate someone who moved
    out: not "in six months".
    """
    coordinator = a_person(db, name="Rina", phone="0500000001", unit="1")
    person = a_person(db, name="Moved out", phone="0500000002", unit="9")
    token = auth.start_session(db, person.id)

    auth.set_status(db, person.id, "deactivated", by_person_id=coordinator.id)

    assert auth.person_for_session(db, token) is None


def test_signing_out_one_device_leaves_the_others_alone(db):
    """Losing a phone shouldn't mean signing out of the one in your hand."""
    person = a_person(db)
    phone = auth.start_session(db, person.id, user_agent="phone")
    tablet = auth.start_session(db, person.id, user_agent="tablet")

    lost = [row for row in auth.sessions_of(db, person.id)
            if row["user_agent"] == "phone"][0]
    auth.end_other_session(db, lost["id"], person.id)

    assert auth.person_for_session(db, phone) is None
    assert auth.person_for_session(db, tablet) is not None


def test_you_cannot_sign_out_somebody_elses_device(db):
    """The owner's id is part of the delete, so a forged id matches nothing."""
    mine = a_person(db, phone="0500000003", unit="3")
    theirs = a_person(db, name="Someone else", phone="0500000004", unit="4")
    their_token = auth.start_session(db, theirs.id)
    their_session = auth.sessions_of(db, theirs.id)[0]

    auth.end_other_session(db, their_session["id"], mine.id)

    assert auth.person_for_session(db, their_token) is not None


# --- approval ----------------------------------------------------------------

def test_a_new_account_may_look_but_not_book(db):
    """Sign-up is open to anyone with the link; acting is not.

    This is the approval gate, checked where it actually bites: the permission
    rules. A waiting resident sees the building so the wait makes sense, and can
    do nothing else.
    """
    waiting = a_person(db, status="pending")
    actor = auth.actor_for(db, waiting)

    assert can(actor, VIEW_SPACES, now=now_utc()) is True
    assert can(actor, BOOK, now=now_utc()) is False


def test_approval_is_what_turns_looking_into_booking(db):
    coordinator = a_person(db, name="Rina", phone="0500000001", unit="1")
    waiting = a_person(db, status="pending", phone="0500000005", unit="5")

    auth.set_status(db, waiting.id, "approved", by_person_id=coordinator.id)

    actor = auth.actor_for(db, auth.get_person(db, waiting.id))
    assert can(actor, BOOK, now=now_utc()) is True


# --- who is asking -----------------------------------------------------------

def test_the_actor_carries_the_rights_a_person_holds_now(db):
    """The permission rules trust the actor, so the actor has to be right."""
    person = a_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, created_at_utc) VALUES ('12', ?)",
        (to_text(now_utc()),),
    ).lastrowid
    db.execute(
        """INSERT INTO space_right
             (space_id, person_id, role, valid_from_utc, created_at_utc)
           VALUES (?, ?, 'owner', ?, ?)""",
        (space_id, person.id, to_text(now_utc() - timedelta(days=1)), to_text(now_utc())),
    )

    actor = auth.actor_for(db, person)
    assert actor.holds(space_id, "owner") is True


def test_a_stand_in_whose_time_is_up_holds_nothing(db):
    """A manager right with an end date simply isn't there afterwards.

    Expiry is handled once, here, rather than in every permission rule. If this
    slipped, someone who covered a neighbour last August would still be able to
    open their space today, and no screen would show why.
    """
    person = a_person(db)
    space_id = db.execute(
        "INSERT INTO space (label, created_at_utc) VALUES ('12', ?)",
        (to_text(now_utc()),),
    ).lastrowid
    db.execute(
        """INSERT INTO space_right
             (space_id, person_id, role, valid_from_utc, valid_to_utc, created_at_utc)
           VALUES (?, ?, 'manager', ?, ?, ?)""",
        (space_id, person.id,
         to_text(now_utc() - timedelta(days=30)),
         to_text(now_utc() - timedelta(days=1)),      # ended yesterday
         to_text(now_utc())),
    )

    actor = auth.actor_for(db, person)
    assert actor.space_roles == {}


def test_a_visitor_with_no_session_can_do_nothing(db):
    """The "nobody" actor exists so no route needs a special case for visitors."""
    actor = auth.actor_for(db, None)
    assert actor.is_signed_in is False
    assert can(actor, VIEW_SPACES, now=now_utc()) is False


# --- the sign-up link --------------------------------------------------------

def test_rotating_the_sign_up_link_retires_the_old_one(db):
    """Used when the link has spread past the building.

    Rotating must not disturb anyone already signed in, which is why the code
    lives in a settings row rather than on each account.
    """
    person = a_person(db)
    token = auth.start_session(db, person.id)

    first = auth.rotate_join_code(db, by_person_id=person.id)
    second = auth.rotate_join_code(db, by_person_id=person.id)

    assert first != second
    assert auth.join_code(db) == second
    assert auth.person_for_session(db, token) is not None
