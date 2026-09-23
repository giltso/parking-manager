"""Commands for whoever runs the server.

Run them as:

    python -m app.cli make-coordinator --name "Dana" --phone 0501234567 --unit 7
    python -m app.cli new-join-code
    python -m app.cli seed-demo

**Why these exist rather than editing the database by hand.** Two reasons.

First, creating a coordinator is not one row: it is a person, a status, a flag,
and a line in the record. Issuing a sign-in link means generating a code,
storing only its fingerprint, and setting an expiry. Done by hand at eleven at
night, while somebody is locked out, that is where the code gets stored instead
of its fingerprint and nobody notices.

Second, every command here goes through the same service functions the website
uses, so each one writes an event marked `maintainer`. That is what makes the
promise in PLAN 11.1 real: the person who runs the server has no hidden powers,
and anything they fix is visible to coordinators afterwards.

`seed-demo` is the exception: it is for filling a throwaway database while
building screens, and it refuses to touch a database that already has people in
it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from app.clock import now_utc, to_text
from app.config import settings
from app.db import connect, migrate, transaction
from app.domain import timeutil as tu
from app.services import auth, events


def make_coordinator(args) -> int:
    """Create (or promote) a coordinator and print a sign-in link for them.

    Needed once on a new deployment, because the first coordinator has nobody to
    approve them, and again if every coordinator loses their phone at once.
    """
    connection = connect()
    migrate(connection)

    phone = auth.normalise_phone(args.phone)
    with transaction(connection) as tx:
        row = tx.execute("SELECT id FROM person WHERE phone = ?", (phone,)).fetchone()

        if row is None:
            cursor = tx.execute(
                """INSERT INTO person
                     (name, phone, unit, locale, status, is_coordinator, created_at_utc)
                   VALUES (?, ?, ?, ?, 'approved', 1, ?)""",
                (args.name, phone, args.unit, settings.default_locale, to_text(now_utc())),
            )
            person_id = cursor.lastrowid
        else:
            person_id = row["id"]
            tx.execute(
                "UPDATE person SET is_coordinator = 1, status = 'approved' WHERE id = ?",
                (person_id,),
            )

        events.record(tx, "person.made_coordinator", actor_kind="maintainer",
                      subject_person_id=person_id, phone=phone)

        # A sign-up code has to exist before anyone can join.
        if auth.join_code(tx) is None:
            auth.rotate_join_code(tx, by_person_id=None, actor_kind="maintainer")

        code = auth.issue_code(tx, person_id, purpose="invite",
                               actor_kind="maintainer")

    print(f"Coordinator ready: {args.name} ({phone})")
    print(f"Sign-in link (one use, {auth.SIGNIN_LINK_DAYS} days):")
    print(f"  {settings.base_url}/signin/{code}")
    return 0


def new_join_code(args) -> int:
    """Replace the building's sign-up link.

    Used when the old link has travelled beyond the building. Nobody already
    signed in is affected.
    """
    connection = connect()
    migrate(connection)
    with transaction(connection) as tx:
        code = auth.rotate_join_code(tx, by_person_id=None, actor_kind="maintainer")

    print("New sign-up link:")
    print(f"  {settings.base_url}/join/{code}")
    return 0


def seed_demo(args) -> int:
    """Fill an empty database with a small pretend building, for local work.

    Enough to click around: a coordinator, two residents, four spaces, and one
    space opened all week. It refuses to run if any person already exists, so it
    can never be pointed at the real building's data by mistake.
    """
    connection = connect()
    migrate(connection)

    existing = connection.execute("SELECT COUNT(*) AS count FROM person").fetchone()
    if existing["count"] > 0:
        print("Refusing to seed: this database already has people in it.", file=sys.stderr)
        return 1

    moment = to_text(now_utc())
    with transaction(connection) as tx:
        auth.rotate_join_code(tx, by_person_id=None, actor_kind="maintainer")

        def add_person(name, phone, unit, coordinator=False):
            return tx.execute(
                """INSERT INTO person
                     (name, phone, unit, locale, status, is_coordinator, created_at_utc)
                   VALUES (?, ?, ?, 'he', 'approved', ?, ?)""",
                (name, phone, unit, 1 if coordinator else 0, moment),
            ).lastrowid

        coordinator_id = add_person("Rina (coordinator)", "+972500000001", "1", True)
        away_id = add_person("Avi (usually away)", "+972500000002", "4")
        here_id = add_person("Dana (usually here)", "+972500000003", "7")

        spaces = {}
        for label, unit in (("12", "4"), ("13", "7"), ("14", "9"), ("15", None)):
            spaces[label] = tx.execute(
                "INSERT INTO space (label, unit, created_at_utc) VALUES (?, ?, ?)",
                (label, unit, moment),
            ).lastrowid

        # Two spaces assigned, as a coordinator would after reading the
        # building's records.
        for space_label, person_id in (("12", away_id), ("13", here_id)):
            tx.execute(
                """INSERT INTO space_right
                     (space_id, person_id, role, valid_from_utc, granted_by, created_at_utc)
                   VALUES (?, ?, 'owner', ?, ?, ?)""",
                (spaces[space_label], person_id, moment, coordinator_id, moment),
            )

        # Avi is usually away, so his space is open all week (PLAN 8.1).
        tx.execute(
            """INSERT INTO rule
                 (space_id, effect, kind, weekdays, start_minute, end_minute,
                  valid_from, created_by, created_at_utc)
               VALUES (?, 'open', 'plan', ?, 0, ?, ?, ?, ?)""",
            (spaces["12"], tu.ALL_WEEK, tu.MINUTES_PER_DAY,
             (now_utc() - timedelta(days=1)).date().isoformat(), away_id, moment),
        )

        code = auth.issue_code(tx, coordinator_id, purpose="invite",
                               actor_kind="maintainer")

    print("Demo building ready.")
    print(f"  Sign in as the coordinator: {settings.base_url}/signin/{code}")
    print(f"  Sign-up link: {settings.base_url}/join/{auth.join_code(connection)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    made = commands.add_parser("make-coordinator", help="create or promote a coordinator")
    made.add_argument("--name", required=True)
    made.add_argument("--phone", required=True)
    made.add_argument("--unit", required=True)
    made.set_defaults(run=make_coordinator)

    rotated = commands.add_parser("new-join-code", help="replace the sign-up link")
    rotated.set_defaults(run=new_join_code)

    demo = commands.add_parser("seed-demo", help="fill an empty database for local work")
    demo.set_defaults(run=seed_demo)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
