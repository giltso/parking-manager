"""Who may do what. The only place in the app that decides.

Two different questions get confused all the time:

* **Authentication** is "who are you?" — the cookie, the sign-in code.
* **Authorisation** is "may you do this?" — this file.

Every screen and every service asks `can(...)` here. None of them decide for
themselves. Scattered checks are how a coordinator-only page ends up reachable
by anyone: one route forgets, and nothing tells you.

Three kinds of permission meet in this file, which is normal for an app like
this. The industry names are worth knowing:

* **RBAC**, role-based: a flag on the person. Ours is `is_coordinator`.
* **ReBAC**, relationship-based: your relationship to one particular thing.
  Owner *of space 12*; host *of booking 9*. This is how shared documents work.
* **Capability token**: holding an unguessable link is itself the permission.
  Ours is the guest link, which can act on exactly one booking.

Rules this file follows:

1. Deny by default. An unknown action returns False.
2. Every check takes `now`, because rights expire (a manager's stand-in ends,
   a guest link dies when the booking does).
3. Coordinators run the building, not private spaces. They assign spaces and
   approve people; they cannot open, block or reclaim someone's space.
4. The server always re-checks. Hiding a button is presentation, not security.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.config import settings

# --- The actions, as constants ----------------------------------------------
# Using constants rather than loose strings means a typo is an error you see
# immediately, instead of a check that quietly answers "no" forever.

VIEW_SPACES = "view_spaces"                 # see the list of spaces and who holds them
BOOK = "book"                               # make a booking on an open space
ACT_ON_BOOKING = "act_on_booking"           # confirm arrival, edit, extend, release, cancel
SET_SPACE_RULES = "set_space_rules"         # open or block a space
RECLAIM_BOOKING = "reclaim_booking"         # cancel someone's booking on your own space
GRANT_SPACE_RIGHT = "grant_space_right"     # add a co-owner or a manager
RELEASE_SPACE = "release_space"             # give up a space you hold
ASSIGN_SPACE = "assign_space"               # give a space to a resident
APPROVE_PERSON = "approve_person"           # let a new sign-up in
MANAGE_SPACES = "manage_spaces"             # add or deactivate spaces
VIEW_COORDINATOR_TOOLS = "view_coordinator_tools"

ALL_ACTIONS = frozenset({
    VIEW_SPACES, BOOK, ACT_ON_BOOKING, SET_SPACE_RULES, RECLAIM_BOOKING,
    GRANT_SPACE_RIGHT, RELEASE_SPACE, ASSIGN_SPACE, APPROVE_PERSON,
    MANAGE_SPACES, VIEW_COORDINATOR_TOOLS,
})


# --- Who is asking ----------------------------------------------------------

@dataclass(frozen=True)
class Actor:
    """Everything the permission rules need to know about whoever is asking.

    Built once per request from the session cookie or the guest link, then
    passed around. It holds no database connection: these rules are pure
    decisions about facts, which makes them fast and easy to test.

    Attributes:
        person_id: the signed-in person, or None for a visitor or a guest link.
        status: their account status ('approved', 'pending', ...).
        is_coordinator: runs the building's side of the app.
        space_roles: for each space they hold a right on *right now*, the set of
            roles they hold, e.g. {12: {"owner"}}. Expired rights are left out
            when this is built, so the rules here don't repeat that check.
        guest_booking_id: set only when someone arrived through a guest link.
            That link may act on that one booking and nothing else.
    """

    person_id: int | None = None
    status: str = "visitor"
    is_coordinator: bool = False
    space_roles: dict[int, set[str]] = field(default_factory=dict)
    guest_booking_id: int | None = None

    # --- small helpers, so the rules below read like sentences --------------

    @property
    def is_signed_in(self) -> bool:
        return self.person_id is not None

    @property
    def is_approved(self) -> bool:
        """A sign-up waiting for approval can look, but not act."""
        return self.status == "approved"

    @property
    def is_guest_link(self) -> bool:
        return self.guest_booking_id is not None

    def holds(self, space_id: int, *roles: str) -> bool:
        """True if this actor holds any of `roles` on that space."""
        held = self.space_roles.get(space_id, set())
        return any(role in held for role in roles)


def visitor() -> Actor:
    """Someone with no session at all: not signed in, not a guest link."""
    return Actor()


def guest(booking_id: int) -> Actor:
    """Someone holding a valid guest link for one booking."""
    return Actor(status="guest", guest_booking_id=booking_id)


# --- What they are asking about ---------------------------------------------

@dataclass(frozen=True)
class BookingFacts:
    """The few things about a booking that permission depends on.

    A small copy rather than the database row, so the rules can't accidentally
    depend on something they shouldn't, and tests need no database.
    """

    id: int
    space_id: int
    host_person_id: int
    start_utc: datetime
    state: str          # 'held', 'parked', 'ended', 'cancelled', 'expired'


@dataclass(frozen=True)
class SpaceFacts:
    """The few things about a space that permission depends on."""

    id: int
    is_active: bool = True


# --- The decision -----------------------------------------------------------

def can(actor: Actor, action: str, resource=None, *, now: datetime) -> bool:
    """May this actor do this action to this resource, at this moment?

    Args:
        actor: who is asking (see `Actor`).
        action: one of the constants above.
        resource: a `SpaceFacts` or `BookingFacts` when the action is about one
            particular thing; None for actions that aren't.
        now: the current moment, from `app.clock.now_utc()`. Passed in rather
            than read here so the rules stay pure and testable.

    Returns:
        True only if the action is allowed. Anything unrecognised is False.
    """
    if action not in ALL_ACTIONS:
        return False                      # deny by default: unknown means no

    # A guest link is a key to one booking, and nothing else in the app.
    if actor.is_guest_link:
        return (
            action == ACT_ON_BOOKING
            and isinstance(resource, BookingFacts)
            and resource.id == actor.guest_booking_id
        )

    if not actor.is_signed_in:
        return False                      # visitors see nothing until they sign in

    # --- things any signed-in person may do ---------------------------------
    if action == VIEW_SPACES:
        # Including someone still waiting for approval: they can look around
        # while they wait, which makes the wait make sense.
        return True

    # Everything past this point needs an approved account.
    if not actor.is_approved:
        return False

    if action == BOOK:
        return True

    if action == ACT_ON_BOOKING:
        # Your own booking. Note that holding the space does NOT let you act on
        # someone else's booking on it: for that, see RECLAIM_BOOKING, which has
        # its own rule.
        return (
            isinstance(resource, BookingFacts)
            and resource.host_person_id == actor.person_id
        )

    # --- things only the people who hold the space may do -------------------
    if action in (SET_SPACE_RULES, GRANT_SPACE_RIGHT, RELEASE_SPACE):
        if not isinstance(resource, SpaceFacts):
            return False
        if action == SET_SPACE_RULES:
            # Owners and their stand-ins may open and block.
            return actor.holds(resource.id, "owner", "manager")
        # Adding people, or giving the space up, is the owner's alone: a
        # stand-in shouldn't be able to hand the space to someone else.
        return actor.holds(resource.id, "owner")

    if action == RECLAIM_BOOKING:
        return _may_reclaim(actor, resource, now=now)

    # --- things only a coordinator may do -----------------------------------
    if action in (ASSIGN_SPACE, APPROVE_PERSON, MANAGE_SPACES, VIEW_COORDINATOR_TOOLS):
        return actor.is_coordinator

    return False                          # unreachable today; still deny


def _may_reclaim(actor: Actor, resource, *, now: datetime) -> bool:
    """May this owner cancel that booking on their space, right now?

    This is the one rule where the person needing a space beats the person who
    owns it, and the building asked for it (PLAN section 8.3):

    * More than `RECLAIM_NOTICE_MINUTES` before the booking starts: yes. The
      client gets a notification and time to find another space.
    * Inside that window: no. They may already be driving over.
    * Once the car is parked: no, ever. Someone has parked and walked away.

    When this returns False the owner isn't stuck: the app stops cancelling and
    shows both phone numbers instead, so the two neighbours sort it out.
    """
    if not isinstance(resource, BookingFacts):
        return False
    if not actor.holds(resource.space_id, "owner", "manager"):
        return False
    if resource.state != "held":
        return False                      # parked, or already over
    notice = timedelta(minutes=settings.reclaim_notice_minutes)
    return resource.start_utc - now > notice


def require(actor: Actor, action: str, resource=None, *, now: datetime) -> None:
    """Same question, but raises `PermissionDenied` instead of returning False.

    Routes use this when the answer must stop the request; templates use `can`
    when they only need to decide whether to draw a button.
    """
    if not can(actor, action, resource, now=now):
        raise PermissionDenied(action)


class PermissionDenied(Exception):
    """Raised when an actor tried something they aren't allowed to do.

    The web layer turns this into a 403 response. It carries the action name so
    the log says what was refused, which is what you want when someone reports
    "the button does nothing".
    """

    def __init__(self, action: str) -> None:
        super().__init__(f"not allowed: {action}")
        self.action = action
