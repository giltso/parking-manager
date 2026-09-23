"""Writing down what happened.

The `event` table is the app's memory. Version 1 deliberately has no rules,
limits or penalties, so this record is how version 2's rules will be decided:
how often bookings go unused, how often owners take their space back, how many
searches found nothing.

Two habits make it worth having:

* **Write the event in the same transaction as the change it describes.** Then
  the record can never disagree with reality, even if the program stops halfway.
* **Never edit or delete a row.** Rows are added and nothing else. A record you
  can quietly rewrite is not a record.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.clock import now_utc, to_text

# Who did it. 'person' is an ordinary resident acting for themselves;
# 'coordinator' is someone using the building tools; 'maintainer' is a
# command-line fix by whoever runs the server, which coordinators can see;
# 'system' is the app itself, for example expiring a booking nobody claimed.
ACTOR_KINDS = ("person", "guest", "coordinator", "maintainer", "system")


def record(
    connection: sqlite3.Connection,
    type: str,
    *,
    actor_kind: str = "person",
    actor_person_id: int | None = None,
    space_id: int | None = None,
    booking_id: int | None = None,
    **detail: Any,
) -> int:
    """Add one line to the record. Returns its id.

    Args:
        connection: the same connection as the change being recorded, so both
            live or die together.
        type: what happened, as `area.thing`: "person.joined", "booking.created".
        actor_kind: which kind of actor did it (see above).
        actor_person_id: which person, when there is one.
        space_id, booking_id: what it was about, when it was about one of those.
        **detail: anything else worth keeping, stored as JSON. Written this way
            so adding a field to one kind of event needs no change to the table.

    Keep `detail` free of secrets: this record is shown to coordinators.
    """
    if actor_kind not in ACTOR_KINDS:
        raise ValueError(f"unknown actor kind: {actor_kind}")

    cursor = connection.execute(
        """INSERT INTO event
             (at_utc, type, space_id, booking_id, actor_person_id, actor_kind, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            to_text(now_utc()),
            type,
            space_id,
            booking_id,
            actor_person_id,
            actor_kind,
            json.dumps(detail, ensure_ascii=False, default=str),
        ),
    )
    return cursor.lastrowid
