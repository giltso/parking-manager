"""Tests for the sign-in screens, as a browser would use them.

**Why these tests exist.** `test_auth.py` proves the rules; these prove the
wiring: that the cookie is set with the right protections, that the approval
gate is actually applied on the screens, that a coordinator page refuses
everyone else, and that a form submitted from another website is rejected.

Every one of these is invisible while things work. A missing `HttpOnly` on a
cookie changes nothing you can see, right up until a stray script reads it.

**How they work.** Through `TestClient`, which runs the whole app in the test
process and speaks to it the way a browser does, cookies included.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import db as app_db
from app.config import settings
from app.main import app
from app.services import auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The app with a throwaway database, and a sign-up code ready to use."""
    test_settings = dataclasses.replace(settings, database_path=str(tmp_path / "web.db"))
    monkeypatch.setattr(app_db, "settings", test_settings)

    with TestClient(app) as running:
        with app.state.db as connection:
            auth.rotate_join_code(connection, by_person_id=None, actor_kind="maintainer")
        # Ask for English on every request, so the assertions below can quote
        # what a reader sees. Hebrew is the app's default, which is what the
        # language test at the bottom of this file checks.
        running.headers["accept-language"] = "en-GB,en"
        yield running


def join(client, name="Dana", phone="0501234567", unit="7"):
    """Sign up through the building's current link, as a resident would."""
    code = auth.join_code(app.state.db)
    return client.post(
        f"/join/{code}",
        data={"name": name, "phone": phone, "unit": unit, "locale": "en"},
        follow_redirects=False,
    )


def make_coordinator(person_id):
    app.state.db.execute(
        "UPDATE person SET is_coordinator = 1, status = 'approved' WHERE id = ?",
        (person_id,),
    )


# --- joining -----------------------------------------------------------------

def test_signing_up_lands_on_the_profile_already_signed_in(client):
    """One form, and you are in: no email to confirm, no password to choose.

    Dropping someone on a sign-in screen straight after signing up is a classic
    way to lose them, so the response must carry a session.
    """
    response = join(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/me"
    assert client.cookies.get("session")


def test_the_session_cookie_is_protected(client):
    """HttpOnly and SameSite are the two settings that make a cookie safe.

    HttpOnly keeps JavaScript from reading it; SameSite stops another site
    sending it with their own requests. Neither is visible in use, so they are
    checked here rather than trusted.
    """
    response = join(client)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_an_old_sign_up_link_no_longer_works(client):
    """Rotating the link is how a coordinator stops it spreading further."""
    stale = auth.join_code(app.state.db)
    with app.state.db as connection:
        auth.rotate_join_code(connection, by_person_id=None, actor_kind="maintainer")

    page = client.get(f"/join/{stale}")
    assert "no longer active" in page.text

    blocked = client.post(
        f"/join/{stale}",
        data={"name": "Someone", "phone": "0509999999", "unit": "9", "locale": "en"},
    )
    assert "no longer active" in blocked.text
    assert app.state.db.execute(
        "SELECT COUNT(*) AS count FROM person"
    ).fetchone()["count"] == 0


def test_a_bad_phone_number_comes_back_with_the_form_still_filled_in(client):
    """Retyping everything after one mistake is where people give up.

    The check is that the other fields survive the round trip, not merely that
    an error appears.
    """
    code = auth.join_code(app.state.db)
    response = client.post(
        f"/join/{code}",
        data={"name": "Dana", "phone": "nonsense", "unit": "7", "locale": "en"},
    )
    assert "Dana" in response.text
    assert 'value="7"' in response.text


# --- the approval gate -------------------------------------------------------

def test_a_new_resident_is_told_they_are_waiting(client):
    """The one thing a waiting resident needs to know, on the page they land on."""
    join(client)
    page = client.get("/me")
    assert "waiting for a coordinator" in page.text


def test_the_coordinator_screen_refuses_an_ordinary_resident(client):
    """Hiding the link is tidiness; this is the part that actually stops them."""
    join(client)
    response = client.get("/coordinator")
    assert response.status_code == 403
    assert "Not allowed" in response.text


def test_a_coordinator_can_approve_a_waiting_resident(client):
    """The whole path: two people, one approves the other, and it sticks."""
    join(client, name="Rina", phone="0500000001", unit="1")
    rina_id = app.state.db.execute("SELECT id FROM person").fetchone()["id"]
    make_coordinator(rina_id)

    resident = TestClient(app)
    join(resident, name="Dana", phone="0500000002", unit="7")
    dana_id = app.state.db.execute(
        "SELECT id FROM person WHERE unit = '7'"
    ).fetchone()["id"]

    client.post(f"/coordinator/people/{dana_id}/status", data={"status": "approved"},
                follow_redirects=False)

    assert app.state.db.execute(
        "SELECT status FROM person WHERE id = ?", (dana_id,)
    ).fetchone()["status"] == "approved"


def test_rejecting_someone_signs_them_out_immediately(client):
    """Not "when their cookie expires": now.

    A coordinator who rejects a sign-up expects it to be over, and the person
    still holding a working session would be a nasty surprise months later.
    """
    join(client, name="Rina", phone="0500000001", unit="1")
    rina_id = app.state.db.execute("SELECT id FROM person").fetchone()["id"]
    make_coordinator(rina_id)

    stranger = TestClient(app)
    join(stranger, name="Not a resident", phone="0509999999", unit="99")
    stranger_id = app.state.db.execute(
        "SELECT id FROM person WHERE unit = '99'"
    ).fetchone()["id"]

    client.post(f"/coordinator/people/{stranger_id}/status", data={"status": "rejected"},
                follow_redirects=False)

    assert stranger.get("/me").status_code == 401


# --- moving to another phone --------------------------------------------------

def test_a_code_from_one_phone_signs_in_another(client):
    """The whole point of device codes: no password, no email, no waiting."""
    join(client)
    shown = client.post("/me/device-code")
    code = shown.text.split('class="code-display" dir="ltr">')[1].split("<")[0].strip()

    other_phone = TestClient(app)
    other_phone.headers["accept-language"] = "en-GB,en"
    response = other_phone.post("/login", data={"code": code}, follow_redirects=False)

    assert response.status_code == 303
    assert other_phone.cookies.get("session")


def test_a_wrong_code_says_only_that_it_is_wrong(client):
    """Never "expired" or "already used": those differences only help a guesser."""
    response = client.post("/login", data={"code": "WRONGCODE"})
    assert response.status_code == 400
    # The apostrophe in "doesn't" is written as &#39; in HTML, so this looks for
    # a fragment without one. That escaping is the template protecting the page
    # from text that could otherwise close a tag.
    assert "work or has expired" in response.text


def test_signing_out_makes_the_cookie_useless(client):
    """The session is deleted, so the cookie cannot be reused if it was copied."""
    join(client)
    token = client.cookies.get("session")
    client.post("/logout", follow_redirects=False)

    assert auth.person_for_session(app.state.db, token) is None


# --- forms from other websites ------------------------------------------------

def test_a_form_submitted_from_another_site_is_refused(client):
    """Cross-site request forgery, and the one line that stops it.

    A page elsewhere can contain a hidden form aimed at this app. A resident who
    is signed in and visits that page submits it without knowing, because their
    browser attaches the cookie as usual. No password is needed: the attack
    borrows a session that is already open.
    """
    join(client)
    response = client.post(
        "/me/plates",
        data={"plate": "12-345-67"},
        headers={"origin": "https://elsewhere.example"},
    )
    assert response.status_code == 403


def test_a_form_from_this_app_is_accepted(client):
    """The same check must not break the app's own forms, which is the risk."""
    join(client)
    response = client.post(
        "/me/plates",
        data={"plate": "12-345-67"},
        headers={"origin": "http://testserver"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert app.state.db.execute("SELECT plate FROM plate").fetchone()["plate"] == "1234567"


# --- language ----------------------------------------------------------------

def test_a_residents_language_follows_their_account_not_the_browser(client):
    """Chosen once, then right on every phone they sign in on.

    A cookie would forget at the next device; the account remembers.
    """
    join(client)
    client.post("/me", data={"name": "Dana", "phone": "0501234567",
                             "unit": "7", "locale": "he"}, follow_redirects=False)

    page = client.get("/me", headers={"accept-language": "en-GB,en;q=0.9"})
    assert 'lang="he"' in page.text
    assert 'dir="rtl"' in page.text
