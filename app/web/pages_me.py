"""A resident's own details: name, phone, apartment, language, cars, devices.

Everything here is about the person asking. No permission checks are needed
beyond "are you signed in", because every query is written against the signed-in
person's own id: a request naming somebody else's plate or session simply
matches no row.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.params import Form as FormParam

from fastapi import Form

from app.clock import now_utc, to_text
from app.db import transaction
from app.services import auth, events
from app.web.deps import Database, SameOrigin, SignedIn, render

router = APIRouter()


def _normalise_plate(typed: str) -> str:
    """Store plates one way: letters and digits only, in capitals.

    `12-345-67` and `1234567` are the same car. Keeping one form means an owner
    can match the plate they see against the one the app shows them.
    """
    return re.sub(r"[^A-Za-z0-9]", "", typed or "").upper()


@router.get("/me")
def me(request: Request, viewer: SignedIn, db: Database):
    """The profile page: details, cars, and the devices signed in."""
    plates = db.execute(
        "SELECT id, plate FROM plate WHERE person_id = ? ORDER BY id",
        (viewer.person.id,),
    ).fetchall()

    return render(
        request, viewer, "me.html",
        plates=plates,
        sessions=auth.sessions_of(db, viewer.person.id),
        device_code=None,
        error=None,
    )


@router.post("/me")
def update_me(
    request: Request,
    viewer: SignedIn,
    db: Database,
    _: SameOrigin,
    name: str = Form(""),
    phone: str = Form(""),
    unit: str = Form(""),
    locale: str = Form("he"),
):
    """Save changed details.

    Changing the language here rather than only with the header button means the
    choice follows the person to their other phone, because it is stored on the
    account rather than in a cookie.
    """
    try:
        with transaction(db) as tx:
            auth.update_profile(tx, viewer.person.id, name=name, phone=phone,
                                unit=unit, locale=locale)
    except ValueError as problem:
        plates = db.execute(
            "SELECT id, plate FROM plate WHERE person_id = ? ORDER BY id",
            (viewer.person.id,),
        ).fetchall()
        response = render(request, viewer, "me.html", plates=plates,
                          sessions=auth.sessions_of(db, viewer.person.id),
                          device_code=None, error=str(problem))
        response.status_code = 400
        return response

    return RedirectResponse("/me", status_code=303)


@router.post("/me/plates")
def add_plate(request: Request, viewer: SignedIn, db: Database, _: SameOrigin,
              plate: str = Form("")):
    """Add a car. Plates are optional, and a person may have several."""
    cleaned = _normalise_plate(plate)
    if cleaned:
        with transaction(db) as tx:
            tx.execute(
                "INSERT INTO plate (person_id, plate, created_at_utc) VALUES (?, ?, ?)",
                (viewer.person.id, cleaned, to_text(now_utc())),
            )
            events.record(tx, "plate.added", actor_person_id=viewer.person.id)
    return RedirectResponse("/me", status_code=303)


@router.post("/me/plates/{plate_id}/remove")
def remove_plate(viewer: SignedIn, db: Database, _: SameOrigin, plate_id: int):
    """Remove a car.

    The person's own id is part of the delete, so a request naming someone
    else's plate matches nothing rather than removing it. Bookings keep the
    plate text they were made with, so history stays true.
    """
    with transaction(db) as tx:
        tx.execute("DELETE FROM plate WHERE id = ? AND person_id = ?",
                   (plate_id, viewer.person.id))
        events.record(tx, "plate.removed", actor_person_id=viewer.person.id)
    return RedirectResponse("/me", status_code=303)


@router.post("/me/device-code")
def device_code(request: Request, viewer: SignedIn, db: Database, _: SameOrigin):
    """Show a short code for signing in on another phone.

    The code is displayed once, here, and only its fingerprint is stored, so
    this page is the only place it ever exists. It lasts ten minutes, which is
    plenty to walk to the other phone and type it.
    """
    with transaction(db) as tx:
        code = auth.issue_code(tx, viewer.person.id, purpose="device")

    plates = db.execute(
        "SELECT id, plate FROM plate WHERE person_id = ? ORDER BY id",
        (viewer.person.id,),
    ).fetchall()

    return render(request, viewer, "me.html", plates=plates,
                  sessions=auth.sessions_of(db, viewer.person.id),
                  device_code=code, error=None)


@router.post("/me/sessions/{session_id}/end")
def end_session(viewer: SignedIn, db: Database, _: SameOrigin, session_id: int):
    """Sign out one of your other devices, for a phone that was lost or sold."""
    with transaction(db) as tx:
        auth.end_other_session(tx, session_id, viewer.person.id)
    return RedirectResponse("/me", status_code=303)
