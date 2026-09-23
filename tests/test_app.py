"""The app starts, answers, and speaks both languages.

`TestClient` runs the whole app in the test process and calls it like a browser
would, without opening a network port. That includes startup, so these tests
also prove the migrations run when the app boots.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import db as app_db
from app import i18n
from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The app, backed by a throwaway database.

    The settings object is read-only, so `dataclasses.replace` makes a copy with
    one field changed, and `monkeypatch` swaps it in for this test only. Tests
    therefore never touch the real database file, and never affect each other.

    Entering the `with` block runs the app's startup, including the migrations.
    """
    test_settings = dataclasses.replace(settings, database_path=str(tmp_path / "app.db"))
    monkeypatch.setattr(app_db, "settings", test_settings)

    with TestClient(app) as running:
        yield running


def test_healthz_reports_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["time_utc"].endswith("+00:00")        # stored times are UTC
    assert body["time_building"] != body["time_utc"]  # shown times are local


def test_home_page_defaults_to_hebrew(client):
    """No cookie, no browser preference: the building's default language."""
    response = client.get("/", headers={"accept-language": ""})
    assert response.status_code == 200
    assert 'lang="he"' in response.text
    assert 'dir="rtl"' in response.text


def test_home_page_follows_the_browser_language(client):
    response = client.get("/", headers={"accept-language": "en-GB,en;q=0.9"})
    assert 'lang="en"' in response.text
    assert 'dir="ltr"' in response.text
    assert "Building Parking" in response.text


def test_choosing_a_language_is_remembered(client):
    response = client.post("/lang", data={"to": "en"}, follow_redirects=False)
    assert response.status_code == 303
    assert client.cookies.get("lang") == "en"

    # The choice wins over what the browser asks for.
    page = client.get("/", headers={"accept-language": "he-IL,he;q=0.9"})
    assert 'lang="en"' in page.text


def test_language_choice_cannot_bounce_a_visitor_off_the_site(client):
    """An open redirect would let a crafted link send residents elsewhere."""
    response = client.post(
        "/lang",
        data={"to": "he"},
        headers={"referer": "https://elsewhere.example/phish"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"


def test_language_choice_returns_to_the_page_you_were_on(client):
    """A referer from this app is kept, so the button doesn't lose your place."""
    response = client.post(
        "/lang",
        data={"to": "en"},
        headers={"referer": "http://testserver/healthz"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/healthz"


def test_an_unknown_language_falls_back_instead_of_failing(client):
    response = client.post("/lang", data={"to": "martian"}, follow_redirects=False)
    assert response.status_code == 303
    assert client.cookies.get("lang") in i18n.LANGUAGES


def test_every_string_exists_in_both_languages():
    """A missing translation shows English inside a Hebrew screen. Catch it here."""
    assert i18n.missing_keys() == {}
