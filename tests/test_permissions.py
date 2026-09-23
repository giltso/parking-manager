"""The permission grid.

Authorisation bugs are silent: nothing crashes when a check is too generous,
and nobody notices until the wrong person opens the wrong screen. So instead of
testing a few interesting cases, this file writes out the whole grid of "who may
do what" and checks every square of it.

If a future change makes coordinators able to block private spaces, a square
flips and a test fails, which is exactly the alarm we want.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import permissions as perm
from app.config import settings

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

SPACE = perm.SpaceFacts(id=12)
OTHER_SPACE = perm.SpaceFacts(id=99)


def booking(host_person_id=1, space_id=12, state="held", starts_in_minutes=180):
    """A booking for the rules to judge, described by how far off its start is."""
    return perm.BookingFacts(
        id=9,
        space_id=space_id,
        host_person_id=host_person_id,
        start_utc=NOW + timedelta(minutes=starts_in_minutes),
        state=state,
    )


# --- the people in the grid --------------------------------------------------

VISITOR = perm.visitor()
WAITING = perm.Actor(person_id=2, status="pending")
RESIDENT = perm.Actor(person_id=1, status="approved")
OWNER = perm.Actor(person_id=3, status="approved", space_roles={12: {"owner"}})
MANAGER = perm.Actor(person_id=4, status="approved", space_roles={12: {"manager"}})
COORDINATOR = perm.Actor(person_id=5, status="approved", is_coordinator=True)
GUEST_LINK = perm.guest(booking_id=9)

EVERYONE = {
    "visitor": VISITOR,
    "waiting for approval": WAITING,
    "resident": RESIDENT,
    "space owner": OWNER,
    "manager": MANAGER,
    "coordinator": COORDINATOR,
    "guest link": GUEST_LINK,
}


# --- the grid ----------------------------------------------------------------
# Each row: (action, resource, {who is allowed}). Everyone else must be refused.

GRID = [
    (perm.VIEW_SPACES, None,
     {"waiting for approval", "resident", "space owner", "manager", "coordinator"}),

    (perm.BOOK, None,
     {"resident", "space owner", "manager", "coordinator"}),

    # A booking made by the resident whose id is 1.
    (perm.ACT_ON_BOOKING, booking(host_person_id=1),
     {"resident", "guest link"}),

    (perm.SET_SPACE_RULES, SPACE,
     {"space owner", "manager"}),

    # Adding a co-owner, or giving the space up, is the owner's alone: a
    # stand-in must not be able to hand the space to someone else.
    (perm.GRANT_SPACE_RIGHT, SPACE, {"space owner"}),
    (perm.RELEASE_SPACE, SPACE, {"space owner"}),

    # Cancelling someone's booking: allowed here because it is three hours off.
    (perm.RECLAIM_BOOKING, booking(host_person_id=1, starts_in_minutes=180),
     {"space owner", "manager"}),

    (perm.ASSIGN_SPACE, None, {"coordinator"}),
    (perm.APPROVE_PERSON, None, {"coordinator"}),
    (perm.MANAGE_SPACES, None, {"coordinator"}),
    (perm.VIEW_COORDINATOR_TOOLS, None, {"coordinator"}),
]


@pytest.mark.parametrize("action, resource, allowed", GRID)
def test_grid(action, resource, allowed):
    """Every person type against every action: allowed exactly where the grid says."""
    for label, actor in EVERYONE.items():
        result = perm.can(actor, action, resource, now=NOW)
        assert result is (label in allowed), (
            f"{label} should {'be allowed to' if label in allowed else 'not be allowed to'} "
            f"{action}"
        )


# --- the rules that depend on the clock --------------------------------------

def test_owner_may_cancel_a_booking_that_is_still_far_off():
    far_off = booking(starts_in_minutes=settings.reclaim_notice_minutes + 1)
    assert perm.can(OWNER, perm.RECLAIM_BOOKING, far_off, now=NOW) is True


def test_owner_may_not_cancel_a_booking_about_to_start():
    """Inside the notice window the client may already be driving over."""
    imminent = booking(starts_in_minutes=settings.reclaim_notice_minutes - 1)
    assert perm.can(OWNER, perm.RECLAIM_BOOKING, imminent, now=NOW) is False


def test_the_notice_window_edge_belongs_to_the_client():
    """Exactly at the limit is refused: the rule is 'more than', not 'at least'."""
    exactly = booking(starts_in_minutes=settings.reclaim_notice_minutes)
    assert perm.can(OWNER, perm.RECLAIM_BOOKING, exactly, now=NOW) is False


def test_owner_may_never_cancel_a_parked_booking():
    """Someone has parked and walked away; a tap must not strand them."""
    parked = booking(state="parked", starts_in_minutes=180)
    assert perm.can(OWNER, perm.RECLAIM_BOOKING, parked, now=NOW) is False


def test_owner_of_another_space_has_no_say():
    outsider = perm.Actor(person_id=6, status="approved", space_roles={99: {"owner"}})
    assert perm.can(outsider, perm.RECLAIM_BOOKING, booking(), now=NOW) is False
    assert perm.can(outsider, perm.SET_SPACE_RULES, SPACE, now=NOW) is False


# --- the guest link ----------------------------------------------------------

def test_a_guest_link_opens_exactly_one_booking():
    assert perm.can(GUEST_LINK, perm.ACT_ON_BOOKING, booking(), now=NOW) is True

    someone_elses = perm.BookingFacts(
        id=10, space_id=12, host_person_id=1, start_utc=NOW, state="held",
    )
    assert perm.can(GUEST_LINK, perm.ACT_ON_BOOKING, someone_elses, now=NOW) is False


def test_a_guest_link_cannot_book_or_view_the_building():
    assert perm.can(GUEST_LINK, perm.BOOK, now=NOW) is False
    assert perm.can(GUEST_LINK, perm.VIEW_SPACES, now=NOW) is False


# --- the safety net ----------------------------------------------------------

def test_an_unknown_action_is_refused_for_everyone():
    """Deny by default: a typo or a renamed action must never open a door."""
    for actor in EVERYONE.values():
        assert perm.can(actor, "reticulate_splines", now=NOW) is False


def test_require_raises_when_refused():
    with pytest.raises(perm.PermissionDenied) as refused:
        perm.require(RESIDENT, perm.ASSIGN_SPACE, now=NOW)
    assert refused.value.action == perm.ASSIGN_SPACE
