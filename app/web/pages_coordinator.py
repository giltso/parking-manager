"""The coordinator's tools.

A coordinator runs the building's side of the app: approving new residents,
issuing a sign-in link to someone who lost their phone, and rotating the sign-up
link when it has spread too far.

What a coordinator deliberately cannot do is open, block or reclaim somebody's
space. Running the building is not the same as controlling private spaces, and
`app/permissions.py` enforces that rather than this file.

Every action here is recorded with `actor_kind="coordinator"`, so the building
can see who approved whom.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db import transaction
from app.permissions import APPROVE_PERSON, VIEW_COORDINATOR_TOOLS, require
from app.clock import now_utc
from app.services import auth
from app.web.deps import Database, SameOrigin, SignedIn, render

router = APIRouter(prefix="/coordinator")


@router.get("")
def overview(request: Request, viewer: SignedIn, db: Database):
    """Everyone in the building, with those waiting for approval first.

    One list rather than separate screens: the waiting list is usually empty,
    and a page that is usually empty is a page nobody opens.
    """
    require(viewer.actor, VIEW_COORDINATOR_TOOLS, now=now_utc())

    people = db.execute(
        """SELECT id, name, phone, unit, status, is_coordinator, created_at_utc
             FROM person
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, unit, name"""
    ).fetchall()

    return render(
        request, viewer, "coordinator_people.html",
        people=people,
        join_link=f"{settings.base_url}/join/{auth.join_code(db) or ''}",
        issued_link=None,
    )


@router.post("/people/{person_id}/status")
def set_status(request: Request, viewer: SignedIn, db: Database, _: SameOrigin,
               person_id: int, status: str = Form(...)):
    """Approve, reject or deactivate an account.

    Rejecting or deactivating also signs that person out everywhere, so access
    stops immediately rather than whenever their cookie happens to expire.
    """
    require(viewer.actor, APPROVE_PERSON, now=now_utc())

    with transaction(db) as tx:
        auth.set_status(tx, person_id, status, by_person_id=viewer.person.id)

    return RedirectResponse("/coordinator", status_code=303)


@router.post("/people/{person_id}/signin-link")
def signin_link(request: Request, viewer: SignedIn, db: Database, _: SameOrigin,
                person_id: int):
    """Issue a one-time sign-in link for someone who lost their phone.

    The link is shown once, here, for the coordinator to pass on however they
    like. It lasts a week and works once. Only its fingerprint is stored, so
    even a coordinator cannot look it up again later.
    """
    require(viewer.actor, APPROVE_PERSON, now=now_utc())

    with transaction(db) as tx:
        code = auth.issue_code(tx, person_id, purpose="invite",
                               by_person_id=viewer.person.id,
                               actor_kind="coordinator")

    people = db.execute(
        """SELECT id, name, phone, unit, status, is_coordinator, created_at_utc
             FROM person
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, unit, name"""
    ).fetchall()

    return render(
        request, viewer, "coordinator_people.html",
        people=people,
        join_link=f"{settings.base_url}/join/{auth.join_code(db) or ''}",
        issued_link=f"{settings.base_url}/signin/{code}",
    )


@router.post("/join-code/rotate")
def rotate_join_code(viewer: SignedIn, db: Database, _: SameOrigin):
    """Replace the building's sign-up link.

    Used when the old link has spread beyond the building. Nobody already signed
    in is affected; only new sign-ups need the new link.
    """
    require(viewer.actor, APPROVE_PERSON, now=now_utc())

    with transaction(db) as tx:
        auth.rotate_join_code(tx, by_person_id=viewer.person.id)

    return RedirectResponse("/coordinator", status_code=303)
