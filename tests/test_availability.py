"""Tests for "when is this space actually free?".

**Why these tests exist.** This is the rule the building agreed to, and the one
nobody can check by looking at a screen: overlapping openings and blocks resolve
to something, and the only way to know it resolves the *right* way is to state
each case and pin it. If this logic is wrong, the app either lends a space its
owner wanted for themselves, or hides a space that was offered. The first breaks
trust with owners, which is the one thing the whole design protects.

**What they cover**, in order:

1. the base state: closed unless somebody opened it;
2. the specificity table from PLAN 5.2, case by case;
3. the tie rule, where closed wins;
4. the two horizons: recurring openings reach a week, one-offs reach further;
5. bookings sitting on top of open time;
6. the helpers the search will use.

**How they work.** Everything is built from plain values: a list of rules, a
list of bookings, a window, and a "now". No database and no clock, so each test
reads as a sentence and runs in microseconds. Times are written in the
building's own clock, because that is how an owner would describe them, and
converted at the edge by `at()`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.clock import BUILDING_TZ
from app.domain import timeutil as tu
from app.domain.availability import (
    CLOSED,
    OPEN,
    Booking,
    Rule,
    compute_timeline,
    occurrences_of,
)

TODAY = date(2026, 9, 22)          # a Tuesday
NOW = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)   # 09:00 in the building


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """A moment written the way a resident would say it: local clock time."""
    return tu.to_instant(day, hour * 60 + minute)


def timeline(rules, bookings=(), *, day=TODAY, from_hour=0, to_hour=24, now=NOW,
             horizon_days=7):
    """Build a timeline for one day, with the settings this app uses.

    A helper rather than repetition, so each test shows only what makes it
    different from the others.
    """
    return compute_timeline(
        rules=list(rules),
        bookings=list(bookings),
        window_start=at(day, from_hour),
        window_end=at(day, to_hour) if to_hour < 24 else tu.to_instant(day, tu.MINUTES_PER_DAY),
        now=now,
        plan_open_horizon_days=horizon_days,
    )


def state_at(line, moment) -> str:
    """What the timeline says about one instant: 'open', 'closed' or 'booked'.

    Reading a single moment is how a person would check ("is it free at two?"),
    and it keeps the assertions short.
    """
    for segment in line.segments:
        if segment.start <= moment < segment.end:
            if segment.booking_id is not None:
                return "booked"
            return OPEN if segment.open else CLOSED
    raise AssertionError(f"{moment} is outside the timeline")


# --- convenient rule builders -----------------------------------------------

def recurring(effect, weekdays, from_hour, to_hour, *, valid_from=None, valid_to=None,
              rule_id=None):
    """A recurring rule, e.g. "open every Tuesday 08:00-18:00"."""
    return Rule(
        id=rule_id,
        effect=effect,
        kind="plan",
        weekdays=weekdays,
        start_minute=from_hour * 60,
        end_minute=to_hour * 60 if to_hour < 24 else tu.MINUTES_PER_DAY,
        valid_from=valid_from or date(2026, 1, 1),
        valid_to=valid_to,
    )


def one_time(effect, day, from_hour, to_hour=None, *, rule_id=None):
    """A one-off rule; `to_hour=None` means "until the owner removes it"."""
    return Rule(
        id=rule_id,
        effect=effect,
        kind="oneoff",
        starts_at=at(day, from_hour),
        ends_at=at(day, to_hour) if to_hour is not None else None,
    )


# --- 1. the base state -------------------------------------------------------

def test_a_space_with_no_rules_is_closed_all_day():
    """Nothing is shared by accident.

    This is the single most important line of the design: a resident who never
    opens the app must never find a stranger in their space. Every other rule
    here is an exception to this one.
    """
    line = timeline(rules=[])
    assert all(not segment.open for segment in line.segments)
    assert state_at(line, at(TODAY, 14)) == CLOSED


# --- 2. the specificity table (PLAN 5.2) -------------------------------------

def test_a_one_time_block_beats_an_open_all_week_rule():
    """"Open all week" plus "closed tonight" means closed tonight.

    The most common real case: an owner shares their space by default and then
    needs it this evening. The one-off is the deliberate, recent instruction, so
    it wins regardless of how much time each rule covers.
    """
    line = timeline([
        recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1),
        one_time(CLOSED, TODAY, 18, 22, rule_id=2),
    ])
    assert state_at(line, at(TODAY, 15)) == OPEN
    assert state_at(line, at(TODAY, 19)) == CLOSED
    assert state_at(line, at(TODAY, 23)) == OPEN


def test_the_rule_covering_less_time_wins():
    """"Open all week 08:00-20:00" plus "closed Tuesdays" means closed on Tuesday.

    Both are recurring and both run forever, so the tie-break is how much time
    each one covers: 84 hours a week against 24. The narrower rule is the more
    deliberate instruction, so it wins.
    """
    line = timeline([
        recurring(OPEN, tu.ALL_WEEK, 8, 20, rule_id=1),           # 84 hours a week
        recurring(CLOSED, tu.TUESDAY, 0, 24, rule_id=2),          # 24 hours a week
    ])
    assert state_at(line, at(TODAY, 12)) == CLOSED                # TODAY is a Tuesday


def test_a_short_daily_block_wins_against_a_long_daily_opening():
    """"Open weekdays 09:00-17:00" plus "closed every day 12:00-13:00".

    Same shape as above but the other way round in the day: the narrow lunchtime
    block (7 hours a week) beats the wide opening (40 hours a week). Two tests
    rather than one, because a wrong comparison could pass one and fail the
    other.
    """
    weekdays = tu.MONDAY | tu.TUESDAY | tu.WEDNESDAY | tu.THURSDAY | tu.FRIDAY
    line = timeline([
        recurring(OPEN, weekdays, 9, 17, rule_id=1),
        recurring(CLOSED, tu.ALL_WEEK, 12, 13, rule_id=2),
    ])
    assert state_at(line, at(TODAY, 10)) == OPEN
    assert state_at(line, at(TODAY, 12, 30)) == CLOSED
    assert state_at(line, at(TODAY, 14)) == OPEN


def test_a_rule_with_an_end_date_beats_one_that_runs_forever():
    """"Open weekdays" forever, plus "closed all week during September".

    An owner who is home for a month sets a rule with dates on it. It covers
    more hours per week than the opening, so the "less time" test alone would
    get this wrong; what settles it is that one rule ends and the other doesn't.
    Something with an end was decided for a reason.
    """
    weekdays = tu.MONDAY | tu.TUESDAY | tu.WEDNESDAY | tu.THURSDAY | tu.FRIDAY
    line = timeline([
        recurring(OPEN, weekdays, 9, 17, rule_id=1),                       # forever
        recurring(CLOSED, tu.ALL_WEEK, 0, 24, rule_id=2,
                  valid_from=date(2026, 9, 1), valid_to=date(2026, 9, 30)),
    ])
    assert state_at(line, at(TODAY, 10)) == CLOSED


def test_a_short_one_time_opening_beats_an_open_ended_block():
    """"Blocked until I undo it", then "open for two hours this afternoon".

    Both are one-offs, so the first test is a draw and the length decides: the
    two-hour opening is narrower than the block with no end. This is what lets
    an owner who blocked their space indefinitely still lend it for an evening
    without undoing anything.
    """
    line = timeline([
        one_time(CLOSED, TODAY, 0, None, rule_id=1),     # no end: until removed
        one_time(OPEN, TODAY, 14, 16, rule_id=2),
    ])
    assert state_at(line, at(TODAY, 13)) == CLOSED
    assert state_at(line, at(TODAY, 15)) == OPEN
    assert state_at(line, at(TODAY, 17)) == CLOSED


# --- 3. the tie -------------------------------------------------------------

def test_when_two_rules_are_identical_the_space_closes():
    """An exact tie closes the space, because the two mistakes are not equal.

    Wrongly closing costs one missed lend. Wrongly opening puts a stranger in
    somebody's space and loses an owner for good. So when the app genuinely
    cannot tell, it protects the owner.
    """
    line = timeline([
        one_time(OPEN, TODAY, 14, 16, rule_id=1),
        one_time(CLOSED, TODAY, 14, 16, rule_id=2),
    ])
    assert state_at(line, at(TODAY, 15)) == CLOSED


# --- 4. how far ahead rules reach --------------------------------------------

def test_a_recurring_opening_stops_at_the_horizon():
    """"Usually away" opens the next week only, not the week after.

    The building asked for this: an owner who set "usually away" months ago
    shouldn't discover bookings a fortnight out. The same rule, asked about two
    different days, gives open and closed.
    """
    rules = [recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1)]

    in_three_days = TODAY + timedelta(days=3)
    assert state_at(timeline(rules, day=in_three_days), at(in_three_days, 12)) == OPEN

    in_ten_days = TODAY + timedelta(days=10)
    assert state_at(timeline(rules, day=in_ten_days), at(in_ten_days, 12)) == CLOSED


def test_a_one_time_opening_reaches_past_the_horizon():
    """A deliberate "available 1-14 October" still counts beyond the week.

    The horizon exists because recurring rules are easy to forget, not because
    the future is dangerous. An owner who picked dates meant them.
    """
    in_ten_days = TODAY + timedelta(days=10)
    line = timeline([one_time(OPEN, in_ten_days, 8, 20, rule_id=1)], day=in_ten_days)
    assert state_at(line, at(in_ten_days, 12)) == OPEN


def test_a_one_time_opening_beats_a_recurring_block_however_far_ahead():
    """An owner who opens specific dates means it, even over their own routine.

    Written after a first attempt at this test asserted the opposite and failed:
    a recurring lunchtime block does NOT survive a one-off opening, because
    "one-time beats recurring" is the first rule, before any measuring. Pinning
    it here makes that precedence deliberate rather than accidental.
    """
    in_ten_days = TODAY + timedelta(days=10)
    line = timeline(
        [
            one_time(OPEN, in_ten_days, 0, None, rule_id=1),
            recurring(CLOSED, tu.ALL_WEEK, 12, 14, rule_id=2),
        ],
        day=in_ten_days,
    )
    assert state_at(line, at(in_ten_days, 13)) == OPEN


def test_the_horizon_only_ever_takes_availability_away():
    """Recurring openings are cut off at the horizon; recurring blocks are not.

    Checked on the rules themselves rather than through a timeline, because the
    combination that would show it there can't arise: beyond the horizon nothing
    recurring can open a space, so there is nothing for a block to argue with.
    The property still has to hold, or a future change could let the horizon
    quietly *open* a space in ten days' time, which would be the worst kind of
    bug here.
    """
    far_off = TODAY + timedelta(days=10)
    window_start, window_end = at(far_off, 8), at(far_off, 20)
    horizon_end = NOW + timedelta(days=7)

    opening = recurring(OPEN, tu.ALL_WEEK, 8, 20, rule_id=1)
    block = recurring(CLOSED, tu.ALL_WEEK, 8, 20, rule_id=2)

    assert occurrences_of(opening, window_start, window_end,
                          open_horizon_end=horizon_end) == []
    assert len(occurrences_of(block, window_start, window_end,
                              open_horizon_end=horizon_end)) == 1


# --- 5. bookings on top ------------------------------------------------------

def test_a_booking_takes_its_time_out_of_an_open_space():
    """Open time with a booking on it is not free, and the rest of the day still is."""
    line = timeline(
        [recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1)],
        [Booking(id=7, start=at(TODAY, 14), end=at(TODAY, 17))],
    )
    assert state_at(line, at(TODAY, 13, 59)) == OPEN
    assert state_at(line, at(TODAY, 14)) == "booked"
    assert state_at(line, at(TODAY, 17)) == OPEN


def test_bookings_that_touch_do_not_overlap():
    """One booking ending at 14:00 leaves 14:00 free for the next.

    Off-by-one in the other direction would waste an hour of every handover, and
    would make two legitimate back-to-back bookings look like a clash.
    """
    line = timeline(
        [recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1)],
        [
            Booking(id=1, start=at(TODAY, 12), end=at(TODAY, 14)),
            Booking(id=2, start=at(TODAY, 14), end=at(TODAY, 16)),
        ],
    )
    assert line.is_bookable(at(TODAY, 16), at(TODAY, 18)) is True
    assert line.is_bookable(at(TODAY, 13), at(TODAY, 15)) is False


def test_asking_to_book_across_a_closed_gap_is_refused():
    """A car cannot leave and come back, so one closed minute in the middle is a no.

    The mistake this guards against is checking only the start and the end of a
    request, which would happily allow a booking straddling a block.
    """
    line = timeline([
        recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1),
        one_time(CLOSED, TODAY, 15, 16, rule_id=2),
    ])
    assert line.is_bookable(at(TODAY, 14), at(TODAY, 17)) is False
    assert line.is_bookable(at(TODAY, 16), at(TODAY, 17)) is True


# --- 6. the helpers the search will use --------------------------------------

def test_the_free_run_around_a_request_is_the_whole_free_stretch():
    """How much free time surrounds a request, which decides which space is offered.

    Searching prefers the space where the request fits most tightly, so it needs
    the *whole* free stretch, not just the requested part. Here the space is
    open all day with bookings until 13:00 and from 18:00, so a request of
    14:00-17:00 sits inside a free run of 13:00-18:00, leaving an hour spare
    either side.
    """
    line = timeline(
        [recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1)],
        [
            Booking(id=1, start=at(TODAY, 8), end=at(TODAY, 13)),
            Booking(id=2, start=at(TODAY, 18), end=at(TODAY, 21)),
        ],
    )
    assert line.free_run_around(at(TODAY, 14), at(TODAY, 17)) == (at(TODAY, 13), at(TODAY, 18))


def test_there_is_no_free_run_around_a_window_that_is_not_free():
    """If the request itself doesn't fit, there is nothing to measure."""
    line = timeline([recurring(OPEN, tu.ALL_WEEK, 0, 24, rule_id=1)],
                    [Booking(id=1, start=at(TODAY, 14), end=at(TODAY, 15))])
    assert line.free_run_around(at(TODAY, 14), at(TODAY, 17)) is None


def test_neighbouring_stretches_that_say_the_same_thing_are_joined():
    """Two rules producing adjacent open time read as one stretch, not two.

    The sweep cuts the day at every rule edge, so without joining, an owner's
    week strip would be drawn as a row of slivers and "the space is free from
    08:00 to 20:00" would be hard to see.
    """
    line = timeline([
        one_time(OPEN, TODAY, 8, 14, rule_id=1),
        one_time(OPEN, TODAY, 14, 20, rule_id=2),
    ])
    open_segments = [segment for segment in line.segments if segment.open]
    assert len(open_segments) == 1
    assert open_segments[0].start == at(TODAY, 8)
    assert open_segments[0].end == at(TODAY, 20)


def test_the_timeline_has_no_gaps_and_covers_exactly_the_window():
    """Every moment of the window belongs to exactly one segment.

    A gap would mean a moment with no answer at all, and whichever screen asked
    about it would have to invent one. This checks the shape of the result
    rather than any particular rule, so it catches sweep mistakes in general.
    """
    line = timeline([
        recurring(OPEN, tu.ALL_WEEK, 8, 20, rule_id=1),
        one_time(CLOSED, TODAY, 12, 13, rule_id=2),
    ])
    assert line.segments[0].start == line.start
    assert line.segments[-1].end == line.end
    for earlier, later in zip(line.segments, line.segments[1:]):
        assert earlier.end == later.start


# --- awkward shapes ----------------------------------------------------------

def test_an_overnight_opening_covers_the_early_morning_of_the_next_day():
    """A night-shift owner's 22:00-06:00 opening is free at 02:00, not closed.

    The rule belongs to the day it starts on, so answering a question about
    Wednesday morning means looking at Tuesday's rules. Forgetting that is the
    classic bug here, and it would quietly hide every overnight opening.
    """
    tomorrow = TODAY + timedelta(days=1)
    line = timeline([recurring(OPEN, tu.TUESDAY, 22, 6, rule_id=1)],
                    day=tomorrow, from_hour=0, to_hour=12)
    assert state_at(line, at(tomorrow, 2)) == OPEN
    assert state_at(line, at(tomorrow, 7)) == CLOSED


def test_an_opening_on_the_day_the_clocks_change_still_ends_at_six():
    """On the short day, "open 08:00-18:00" still ends at 18:00 on the clock.

    Residents read the clock, not elapsed hours. This is the whole reason
    recurring rules are stored as wall-clock times, checked here end to end
    rather than only inside the time helpers.
    """
    spring = date(2026, 3, 27)
    line = timeline([recurring(OPEN, tu.ALL_WEEK, 8, 18, rule_id=1)], day=spring)
    open_segments = [segment for segment in line.segments if segment.open]
    assert len(open_segments) == 1
    assert open_segments[0].end.astimezone(BUILDING_TZ).hour == 18


@pytest.mark.parametrize("bad_window", [(14, 14), (17, 14)])
def test_a_window_that_does_not_move_forward_is_refused(bad_window):
    """Asking about zero or negative time is a bug in the caller, not a state.

    Raising here means the mistake surfaces at its source, instead of returning
    an empty timeline that some screen then renders as "closed".
    """
    from_hour, to_hour = bad_window
    with pytest.raises(ValueError):
        compute_timeline(
            rules=[], bookings=[],
            window_start=at(TODAY, from_hour), window_end=at(TODAY, to_hour),
            now=NOW, plan_open_horizon_days=7,
        )
