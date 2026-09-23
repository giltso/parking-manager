"""When is a space actually free?

This is the question the whole app is built around, and it has exactly one
answer, produced here. Every screen goes through `compute_timeline`: the search,
the owner's week strip, booking, extending. Two places working it out
separately would eventually disagree, and the app would offer a space it then
refused to book.

The rules, as approved with the building (PLAN.md sections 5 and 4):

1. A space is **closed** unless an owner opened it. Nothing is shared by accident.
2. Openings and blocks overlap freely. The **most specific** one wins:
   a. a one-time rule beats a recurring one, because it was made just now for
      a reason, while a recurring rule was set months ago;
   b. otherwise the rule covering **less time overall** wins, since a narrower
      instruction is the more deliberate one;
   c. if they are still equal, **closed** wins, because the cost of wrongly
      closing a space is a lost lend, and the cost of wrongly opening one is a
      stranger in someone's space.
3. Time opened by a **recurring** rule is only real for the next few days
   (`plan_open_horizon_days`). An owner who chose "usually away" months ago
   shouldn't find bookings weeks out. Blocks are never limited this way: a
   block is always safe to honour.
4. A booking sits on top. Its time is taken whatever the rules say.

The technique is a **sweep line**: collect every moment where something could
change, then look at the stretches between those moments. Nothing changes in
the middle of a stretch, so each one is decided once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.timeutil import (
    MINUTES_PER_DAY,
    Occurrence,
    clip,
    count_weekdays,
    falls_on,
    local_dates_touching,
    to_instant,
    window_minutes,
)

OPEN = "open"
CLOSED = "closed"


# --- what goes in -----------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """An opening or a block, in the shape this module needs.

    Two kinds, matching the database (PLAN 4.5):

    * `kind="plan"`: recurring. Local wall-clock: weekdays, minutes past
      midnight, and the dates it applies between.
    * `kind="oneoff"`: a single stretch, already exact moments.
    """

    id: int | None
    effect: str                    # OPEN or CLOSED
    kind: str                      # 'plan' or 'oneoff'

    # recurring only
    weekdays: int = 0
    start_minute: int = 0
    end_minute: int = 0
    valid_from: date | None = None
    valid_to: date | None = None   # None: no end date

    # one-off only
    starts_at: datetime | None = None
    ends_at: datetime | None = None  # None: until the owner removes it


@dataclass(frozen=True)
class Booking:
    """A booking, reduced to what availability cares about."""

    id: int
    start: datetime
    end: datetime


# --- what comes out ---------------------------------------------------------

@dataclass(frozen=True)
class Segment:
    """A stretch of time where nothing changes.

    `open` says whether the owner's rules allow parking. `booking_id` says
    whether someone already has it. Both matter: a booked stretch of an open
    space is not free, and an open stretch with no booking is.
    """

    start: datetime
    end: datetime
    open: bool
    rule_id: int | None = None
    booking_id: int | None = None

    @property
    def free(self) -> bool:
        """Open, and nobody has taken it."""
        return self.open and self.booking_id is None


@dataclass(frozen=True)
class Timeline:
    """The answer for one space over one window: the segments, in order.

    Segments never overlap and never leave gaps, so the timeline reads like a
    strip from the start of the window to its end.
    """

    start: datetime
    end: datetime
    segments: tuple[Segment, ...]

    def is_bookable(self, start: datetime, end: datetime) -> bool:
        """Could a booking run from `start` to `end`?

        Only if every moment in between is open and unbooked. One closed minute
        in the middle is enough to say no: a car cannot leave and come back.
        """
        if start >= end:
            return False
        if start < self.start or end > self.end:
            raise ValueError("asked about time outside this timeline")

        return all(
            segment.free
            for segment in self.segments
            if segment.start < end and segment.end > start
        )

    def free_run_around(self, start: datetime, end: datetime) -> tuple[datetime, datetime] | None:
        """The whole free stretch containing this window, or None if it isn't free.

        Used when searching: a space free from 13:00 to 18:00 for a request of
        14:00 to 17:00 leaves an hour either side, and those leftovers decide
        which space gets offered (PLAN 6.1).
        """
        if not self.is_bookable(start, end):
            return None

        # Start from the segments the window sits in, then walk outwards over
        # neighbours that are also free and join on with no gap. Walking from
        # the window itself (rather than looking for segments that touch its
        # edges) is what makes this work when the window sits in the middle of
        # one long free segment.
        inside = [
            index for index, segment in enumerate(self.segments)
            if segment.start < end and segment.end > start
        ]
        first, last = inside[0], inside[-1]

        while first > 0:
            previous = self.segments[first - 1]
            if not previous.free or previous.end != self.segments[first].start:
                break
            first -= 1

        while last < len(self.segments) - 1:
            following = self.segments[last + 1]
            if not following.free or following.start != self.segments[last].end:
                break
            last += 1

        return self.segments[first].start, self.segments[last].end


# --- measuring how specific a rule is ---------------------------------------

def _coverage(rule: Rule) -> tuple[float, float]:
    """How much time a rule covers: (over its whole life, in an average week).

    This is what "more specific" means here: a rule covering less time is a
    narrower instruction. "Closed on Saturdays" covers 24 hours a week; "open
    all week, 08:00 to 20:00" covers 84, so Saturday's block wins.

    A rule with no end date covers an unlimited amount of time, written here as
    infinity, which compares correctly against any real number. A rule that runs
    for one month therefore beats an open-ended one, which is what an owner
    means by "closed while I'm home in August".
    """
    if rule.kind == "oneoff":
        if rule.ends_at is None:
            return (float("inf"), 0.0)
        minutes = (rule.ends_at - rule.starts_at).total_seconds() / 60
        return (minutes, 0.0)

    daily = window_minutes(rule.start_minute, rule.end_minute)
    weekly = daily * count_weekdays(rule.weekdays)

    if rule.valid_to is None:
        return (float("inf"), weekly)

    # Count the matching days between the two dates, inclusive.
    days = 0
    day = rule.valid_from
    while day <= rule.valid_to:
        if falls_on(rule.weekdays, day):
            days += 1
        day += timedelta(days=1)
    return (days * daily, weekly)


def _specificity(occurrence: Occurrence) -> tuple:
    """The sort key that decides which rule wins. Smaller is more specific.

    In order:
      1. one-off before recurring;
      2. less total time covered;
      3. less time covered per week (separates two open-ended recurring rules);
      4. closed before open, so an exact tie closes the space.
    """
    return (
        0 if occurrence.kind == "oneoff" else 1,
        occurrence.coverage_minutes,
        occurrence.weekly_minutes,
        0 if occurrence.effect == CLOSED else 1,
    )


# --- turning rules into concrete stretches ----------------------------------

def occurrences_of(
    rule: Rule,
    window_start: datetime,
    window_end: datetime,
    *,
    open_horizon_end: datetime | None = None,
) -> list[Occurrence]:
    """Every stretch this rule produces inside the window.

    Args:
        rule: the opening or block.
        window_start, window_end: the window being asked about.
        open_horizon_end: the moment past which *recurring openings* stop
            counting. Blocks and one-offs ignore it.
    """
    coverage, weekly = _coverage(rule)

    def make(start: datetime, end: datetime) -> Occurrence | None:
        if (
            open_horizon_end is not None
            and rule.kind == "plan"
            and rule.effect == OPEN
        ):
            end = min(end, open_horizon_end)
        trimmed = clip(start, end, window_start, window_end)
        if trimmed is None:
            return None
        return Occurrence(
            start=trimmed[0],
            end=trimmed[1],
            effect=rule.effect,
            kind=rule.kind,
            rule_id=rule.id,
            coverage_minutes=coverage,
            weekly_minutes=weekly,
        )

    if rule.kind == "oneoff":
        # An open-ended one-off ("until I undo it") runs to the end of the window.
        end = rule.ends_at if rule.ends_at is not None else window_end
        made = make(rule.starts_at, end)
        return [made] if made else []

    found: list[Occurrence] = []
    for day in local_dates_touching(window_start, window_end):
        if not falls_on(rule.weekdays, day):
            continue
        if rule.valid_from and day < rule.valid_from:
            continue
        if rule.valid_to and day > rule.valid_to:
            continue

        # The window keeps its wall-clock length, so 08:00-18:00 stays ten
        # hours on the building's clock even on the day the clocks change,
        # when it is nine or eleven hours of real time.
        length = window_minutes(rule.start_minute, rule.end_minute)
        finish = rule.start_minute + length
        start = to_instant(day, rule.start_minute)
        end = to_instant(day + timedelta(days=finish // MINUTES_PER_DAY),
                         finish % MINUTES_PER_DAY)

        made = make(start, end)
        if made:
            found.append(made)

    return found


# --- the sweep --------------------------------------------------------------

def compute_timeline(
    rules: list[Rule],
    bookings: list[Booking],
    window_start: datetime,
    window_end: datetime,
    *,
    now: datetime,
    plan_open_horizon_days: int,
) -> Timeline:
    """Work out the state of one space, moment by moment, across a window.

    Args:
        rules: that space's openings and blocks (deleted ones already left out).
        bookings: its held and parked bookings; anything else is over.
        window_start, window_end: the window to describe.
        now: the current moment, which decides how far recurring openings reach.
        plan_open_horizon_days: how many days ahead a recurring opening counts.

    Returns:
        A `Timeline` covering exactly the window, with no gaps.
    """
    if window_start >= window_end:
        raise ValueError("window must start before it ends")

    horizon_end = now + timedelta(days=plan_open_horizon_days)

    occurrences: list[Occurrence] = []
    for rule in rules:
        occurrences.extend(
            occurrences_of(rule, window_start, window_end, open_horizon_end=horizon_end)
        )

    trimmed_bookings = [
        Booking(booking.id, *clipped)
        for booking in bookings
        if (clipped := clip(booking.start, booking.end, window_start, window_end))
    ]

    # Every moment where something could change: a rule starting or ending, a
    # booking starting or ending, and the window's own edges. Between two
    # neighbouring moments nothing changes, so each stretch is decided once.
    edges = {window_start, window_end}
    for occurrence in occurrences:
        edges.update((occurrence.start, occurrence.end))
    for booking in trimmed_bookings:
        edges.update((booking.start, booking.end))
    ordered = sorted(edges)

    pieces: list[Segment] = []
    for piece_start, piece_end in zip(ordered, ordered[1:]):
        covering = [
            occurrence for occurrence in occurrences
            if occurrence.start <= piece_start and occurrence.end >= piece_end
        ]
        if covering:
            winner = min(covering, key=_specificity)
            is_open = winner.effect == OPEN
            rule_id = winner.rule_id
        else:
            is_open, rule_id = False, None     # nothing said otherwise: closed

        taken = next(
            (booking for booking in trimmed_bookings
             if booking.start <= piece_start and booking.end >= piece_end),
            None,
        )

        pieces.append(Segment(
            start=piece_start,
            end=piece_end,
            open=is_open,
            rule_id=rule_id,
            booking_id=taken.id if taken else None,
        ))

    return Timeline(window_start, window_end, tuple(_merge(pieces)))


def _merge(pieces: list[Segment]) -> list[Segment]:
    """Join neighbouring stretches that say the same thing.

    The sweep cuts at every edge, so an opening made of two adjacent daily
    rules arrives as two pieces. Joining them means a week strip draws one bar
    rather than a row of slivers, and tests read the way a person would
    describe the day.
    """
    merged: list[Segment] = []
    for piece in pieces:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.end == piece.start
            and previous.open == piece.open
            and previous.booking_id == piece.booking_id
        ):
            merged[-1] = Segment(
                start=previous.start,
                end=piece.end,
                open=piece.open,
                # Only keep the rule when both pieces came from the same one,
                # so nothing claims a stretch it didn't produce.
                rule_id=previous.rule_id if previous.rule_id == piece.rule_id else None,
                booking_id=piece.booking_id,
            )
        else:
            merged.append(piece)
    return merged
