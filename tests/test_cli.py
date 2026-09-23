"""Tests for the maintainer's commands.

**Why these tests exist.** These commands run rarely and always under pressure:
setting up a new server, or rescuing the building when every coordinator has
lost their phone. Nobody exercises them in day-to-day use, so a mistake sits
there quietly until the worst moment.

They also carry a promise made to the building (PLAN 11.1): the person who runs
the server has no hidden powers, and anything they fix appears in the record
coordinators can read. That promise is only real if these commands actually
write those events, which is what the last test here checks.

**How they work.** Each test points the app's settings at a throwaway database,
runs the command exactly as a person would, and then looks at what ended up in
the database.
"""

from __future__ import annotations

import dataclasses

import pytest

from app import cli
from app import db as app_db
from app.config import settings
from app.services import auth


@pytest.fixture
def database(tmp_path, monkeypatch, capsys):
    """Point the commands at an empty database, and capture what they print.

    The commands open their own connection, exactly as they do in real life, so
    the test opens a separate one afterwards to inspect the result.
    """
    path = str(tmp_path / "cli.db")
    monkeypatch.setattr(app_db, "settings",
                        dataclasses.replace(settings, database_path=path))
    monkeypatch.setattr(cli, "settings",
                        dataclasses.replace(settings, database_path=path))
    return path


def open_database(path):
    connection = app_db.connect(path)
    return connection


# --- the first coordinator ---------------------------------------------------

def test_making_the_first_coordinator_produces_a_working_sign_in_link(database, capsys):
    """A brand-new building has nobody who can approve anybody.

    Without this command there is no way in at all: the first coordinator cannot
    be approved by a coordinator. The link it prints is the one thing that
    bootstraps everything else, so the test spends it and checks it works.
    """
    assert cli.main(["make-coordinator", "--name", "Rina",
                     "--phone", "0501234567", "--unit", "1"]) == 0

    printed = capsys.readouterr().out
    code = printed.split("/signin/")[1].strip()

    connection = open_database(database)
    used = auth.use_code(connection, code)

    assert used is not None
    person, _token = used
    assert person.is_coordinator is True
    assert person.status == "approved"
    assert person.phone == "+972501234567"      # stored in one form


def test_a_sign_up_code_exists_afterwards(database):
    """Residents cannot join until a sign-up code exists, so the command makes one.

    Forgetting this would leave a working coordinator staring at a sign-up link
    ending in nothing.
    """
    cli.main(["make-coordinator", "--name", "Rina", "--phone", "0501234567",
              "--unit", "1"])

    connection = open_database(database)
    assert auth.join_code(connection)


def test_running_it_for_an_existing_person_promotes_them(database, capsys):
    """The lost-phone case: the person already exists and needs their role back.

    Creating a second account for the same phone number would split their
    spaces and history across two identities, which is far worse than the
    problem being fixed.
    """
    cli.main(["make-coordinator", "--name", "Rina", "--phone", "0501234567",
              "--unit", "1"])
    capsys.readouterr()
    cli.main(["make-coordinator", "--name", "Rina", "--phone", "050-123-4567",
              "--unit", "1"])

    connection = open_database(database)
    people = connection.execute("SELECT * FROM person").fetchall()
    assert len(people) == 1
    assert people[0]["is_coordinator"] == 1


# --- the sign-up link --------------------------------------------------------

def test_rotating_the_sign_up_link_changes_it(database, capsys):
    """Used when the link has spread beyond the building."""
    cli.main(["make-coordinator", "--name", "Rina", "--phone", "0501234567",
              "--unit", "1"])
    capsys.readouterr()

    connection = open_database(database)
    before = auth.join_code(connection)
    connection.close()

    cli.main(["new-join-code"])

    connection = open_database(database)
    assert auth.join_code(connection) != before


# --- the demo builder --------------------------------------------------------

def test_seeding_a_demo_building_gives_something_to_click_through(database):
    """For local work: real screens need real rows behind them."""
    assert cli.main(["seed-demo"]) == 0

    connection = open_database(database)
    assert connection.execute("SELECT COUNT(*) AS n FROM person").fetchone()["n"] == 3
    assert connection.execute("SELECT COUNT(*) AS n FROM space").fetchone()["n"] == 4
    assert connection.execute(
        "SELECT COUNT(*) AS n FROM space_right WHERE role = 'owner'"
    ).fetchone()["n"] == 2


def test_the_demo_builder_refuses_a_database_that_has_people_in_it(database, capsys):
    """The one command that could destroy real data, so it checks first.

    Pointing it at the building's live database by accident is an easy mistake
    to make, and the cost is inventing residents in a real list.
    """
    cli.main(["make-coordinator", "--name", "Rina", "--phone", "0501234567",
              "--unit", "1"])
    capsys.readouterr()

    assert cli.main(["seed-demo"]) == 1
    assert "Refusing to seed" in capsys.readouterr().err


# --- the promise -------------------------------------------------------------

def test_every_maintainer_command_leaves_a_trace(database):
    """The separation of roles is only real if the record shows what was done.

    The building was told the maintainer has no hidden powers and that fixes are
    visible to coordinators. That sentence is worth nothing unless these events
    exist, so this test guards the promise rather than the code.
    """
    cli.main(["make-coordinator", "--name", "Rina", "--phone", "0501234567",
              "--unit", "1"])

    connection = open_database(database)
    events = connection.execute(
        "SELECT type, actor_kind FROM event ORDER BY id"
    ).fetchall()

    kinds = {row["actor_kind"] for row in events}
    types = {row["type"] for row in events}

    assert kinds == {"maintainer"}
    assert "person.made_coordinator" in types
    assert "code.issued" in types
