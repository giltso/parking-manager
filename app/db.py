"""Opening the database, and keeping its shape up to date.

The whole app stores its data in one SQLite file. SQLite is a database that
lives in a single file instead of a separate server program, which suits one
building: nothing extra to run, and a backup is a file copy.

Two jobs live here:

1. `connect()` opens a connection with the right settings. SQLite's defaults are
   cautious and old, and three of them need changing every single time.
2. `migrate()` brings a database file up to the current shape by running any
   numbered SQL files it hasn't run yet.

Nothing here knows what a booking is. Meaning lives in the service layer.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.clock import now_utc, to_text
from app.config import settings

# Where the numbered .sql files live, next to this file.
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(database_path: str | None = None) -> sqlite3.Connection:
    """Open the database with the settings this app depends on.

    Three settings are applied to every connection, because SQLite applies them
    per connection rather than storing them in the file:

    * `foreign_keys = ON` makes SQLite actually enforce the links between
      tables. It is OFF by default, which silently allows a booking that points
      at a person who doesn't exist.
    * `journal_mode = WAL` ("write-ahead log") lets readers keep reading while a
      write is in progress, instead of everyone queueing.
    * `busy_timeout` tells a blocked connection to wait a few seconds for its
      turn rather than failing immediately.

    `row_factory` makes rows behave like dictionaries, so code reads
    `row["state"]` instead of `row[7]` and doesn't break when a column moves.
    """
    path = Path(database_path or settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        path,
        # We manage transactions ourselves (see `transaction`), so Python's
        # automatic handling is turned off.
        isolation_level=None,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Group several writes so that either all of them happen, or none do.

    A transaction is the database's "all or nothing" bracket. Cancelling a
    booking means changing the booking *and* writing a log entry; if the program
    died between the two, the history would lie about what happened. Inside a
    transaction, a failure undoes everything since the start.

    `BEGIN IMMEDIATE` claims the right to write straight away, instead of
    waiting until the first write. That matters for double-booking: SQLite
    allows only one writer at a time, so two people booking the same space at
    the same instant are forced into a queue. The second one then re-checks
    availability and finds the space taken, instead of both succeeding.

    Usage:
        with transaction(conn) as tx:
            tx.execute(...)
            tx.execute(...)
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except Exception:
        connection.execute("ROLLBACK")   # undo everything in this block
        raise
    connection.execute("COMMIT")         # make it permanent


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    """Which migrations this file has already had, as a set of numbers."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version        INTEGER PRIMARY KEY,
            applied_at_utc TEXT NOT NULL
        )
        """
    )
    rows = connection.execute("SELECT version FROM schema_version").fetchall()
    return {row["version"] for row in rows}


def migration_files() -> list[tuple[int, Path]]:
    """Every migration on disk, oldest first, as (number, file).

    Files are named `001_initial.sql`, `002_….sql`, and the leading number is
    both the order and the identity. Sorting by that number, rather than by
    file name, keeps 010 after 009.
    """
    found: list[tuple[int, Path]] = []
    for file in MIGRATIONS_DIR.glob("*.sql"):
        number_text = file.name.split("_", 1)[0]
        if not number_text.isdigit():
            raise ValueError(f"migration {file.name} must start with a number")
        found.append((int(number_text), file))
    found.sort(key=lambda pair: pair[0])
    return found


def migrate(connection: sqlite3.Connection) -> list[int]:
    """Apply every migration this database hasn't had yet. Returns their numbers.

    Running this on an up-to-date database does nothing, so it is safe to call
    on every startup. That is the point: a fresh file and a file from last month
    both end up in exactly the same shape.

    An applied migration is never edited afterwards. A correction is a new file,
    because databases that already ran the old version will never see an edit.
    """
    already = _applied_versions(connection)
    applied: list[int] = []

    for version, file in migration_files():
        if version in already:
            continue
        sql = file.read_text(encoding="utf-8")

        if "BEGIN" in sql.upper() or "COMMIT" in sql.upper():
            raise ValueError(
                f"migration {file.name} must not manage its own transaction; "
                "the runner does that"
            )

        # A migration is applied inside one transaction, so a statement that
        # fails halfway leaves the database exactly as it was, rather than
        # half-changed with no record of it.
        #
        # The BEGIN has to be inside the script rather than around it, because
        # `executescript` commits whatever is open before it starts. Putting
        # BEGIN first means the script's own statements are the transaction,
        # which is then still open for the schema_version row below.
        connection.executescript("BEGIN IMMEDIATE;\n" + sql)
        try:
            connection.execute(
                "INSERT INTO schema_version (version, applied_at_utc) VALUES (?, ?)",
                (version, to_text(now_utc())),
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

        applied.append(version)

    return applied
