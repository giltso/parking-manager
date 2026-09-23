-- Migration 001: the whole starting shape of the database.
--
-- Read this file top to bottom to understand what the app stores. Tables come
-- in dependency order: something is only mentioned after it exists.
--
-- Conventions used throughout (PLAN.md section 4.0):
--   * every table has `id INTEGER PRIMARY KEY`, a number SQLite fills in
--   * moments in time are TEXT like '2026-09-23T14:05:00Z', always UTC
--   * true/false are INTEGER 0 or 1, because SQLite has no boolean type
--   * CHECK (...) lists the only values a column may hold, so a typo in the
--     Python code is refused by the database instead of quietly stored
--   * nothing is ever deleted: rows get an end date or a status
--
-- This file is finished. Corrections go in 002_*.sql, never here, because
-- databases that already ran this version will never see an edit.


-- People ---------------------------------------------------------------------
-- Everyone with an account: residents, coordinators, the developer.
-- Guests are deliberately absent: they have no account and no row (PLAN 9).
CREATE TABLE person (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL,              -- shown only in the situations in PLAN 8.6
    unit            TEXT NOT NULL,              -- apartment; links a person to their space
    locale          TEXT NOT NULL DEFAULT 'he'
                    CHECK (locale IN ('he', 'en')),
    -- A sign-up starts as 'pending' and can do nothing until a coordinator
    -- approves it. Deactivation replaces deletion so the history survives.
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'deactivated')),
    -- Coordinators run the building's side of the app. They cannot open or
    -- block anyone's space: see app/permissions.py.
    is_coordinator  INTEGER NOT NULL DEFAULT 0 CHECK (is_coordinator IN (0, 1)),
    created_at_utc  TEXT NOT NULL
);

-- Licence plates -------------------------------------------------------------
-- Optional, and a person may have several. Deliberately NOT unique: two people
-- in one household legitimately share a car.
CREATE TABLE plate (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES person(id),
    plate           TEXT NOT NULL,              -- stored normalised: letters and digits only
    created_at_utc  TEXT NOT NULL
);
CREATE INDEX plate_by_person ON plate(person_id);


-- Spaces ---------------------------------------------------------------------
-- The numbered spaces painted on the car park floor. A coordinator enters them
-- once, with the apartment each belongs to, from the building's own records.
CREATE TABLE space (
    id              INTEGER PRIMARY KEY,
    label           TEXT NOT NULL UNIQUE,       -- '12', 'B-4': text, because not every building numbers plainly
    unit            TEXT,                       -- the apartment it belongs to; null if it belongs to the building
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at_utc  TEXT NOT NULL
);


-- Who holds a space ----------------------------------------------------------
-- A coordinator assigns each space to its resident, who becomes its owner. The
-- owner may add a co-owner (another 'owner' row) or a manager who stands in
-- while they are away.
--
-- Rights are never deleted. Ending one sets valid_to_utc and status='ended', so
-- "who held space 12 last March" stays answerable.
CREATE TABLE space_right (
    id              INTEGER PRIMARY KEY,
    space_id        INTEGER NOT NULL REFERENCES space(id),
    person_id       INTEGER NOT NULL REFERENCES person(id),
    role            TEXT NOT NULL CHECK (role IN ('owner', 'manager')),
    valid_from_utc  TEXT NOT NULL,
    valid_to_utc    TEXT,                       -- null: no end date planned
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'ended')),
    granted_by      INTEGER REFERENCES person(id),   -- the coordinator or owner who created it
    ended_reason    TEXT CHECK (ended_reason IS NULL OR ended_reason IN
                        ('released', 'revoked', 'coordinator_revoked',
                         'coordinator_replaced', 'expired')),
    created_at_utc  TEXT NOT NULL
);
CREATE INDEX space_right_by_space  ON space_right(space_id, status);
CREATE INDEX space_right_by_person ON space_right(person_id, status);


-- Openings and blocks --------------------------------------------------------
-- One table covers both "available every Tuesday 08:00-18:00" and "closed
-- tonight". Two shapes share it:
--
--   kind='plan'    recurring, stored in the building's own clock time:
--                  weekdays + start_minute/end_minute + valid_from/valid_to dates
--   kind='oneoff'  a single stretch, stored as exact moments in UTC
--
-- Why the split: "08:00 every Tuesday" must stay 08:00 when the clocks change,
-- so it cannot be stored as a fixed moment. A one-off is a specific stretch of
-- real time, so storing it as moments avoids the hour that happens twice each
-- October.
--
-- The CHECK at the bottom enforces that each kind fills exactly its own
-- columns, so a half-filled rule cannot reach the database.
CREATE TABLE rule (
    id              INTEGER PRIMARY KEY,
    space_id        INTEGER NOT NULL REFERENCES space(id),
    effect          TEXT NOT NULL CHECK (effect IN ('open', 'closed')),
    kind            TEXT NOT NULL CHECK (kind IN ('plan', 'oneoff')),

    -- recurring rules only
    weekdays        INTEGER,                    -- bit per weekday: Mon=1, Tue=2, Wed=4, ... Sun=64
    start_minute    INTEGER,                    -- 0..1439, minutes past local midnight
    end_minute      INTEGER,                    -- 1..1440; 1440 means midnight at the end of the day
    valid_from      TEXT,                       -- local date 'YYYY-MM-DD'
    valid_to        TEXT,                       -- local date, inclusive; null: no end

    -- one-off rules only
    starts_at_utc   TEXT,
    ends_at_utc     TEXT,                       -- null means "until the owner removes it"

    created_by      INTEGER NOT NULL REFERENCES person(id),
    created_at_utc  TEXT NOT NULL,
    deleted_at_utc  TEXT,                       -- removed rules are kept, for the record

    CHECK (
        (kind = 'plan'
            AND weekdays IS NOT NULL
            AND start_minute BETWEEN 0 AND 1439
            AND end_minute BETWEEN 1 AND 1440
            AND start_minute <> end_minute      -- equal would mean a zero-length or 24h window; say 0..1440 instead
            AND valid_from IS NOT NULL
            AND starts_at_utc IS NULL AND ends_at_utc IS NULL)
        OR
        (kind = 'oneoff'
            AND starts_at_utc IS NOT NULL
            AND weekdays IS NULL AND start_minute IS NULL AND end_minute IS NULL
            AND valid_from IS NULL AND valid_to IS NULL)
    )
);
CREATE INDEX rule_by_space ON rule(space_id, deleted_at_utc);


-- Bookings -------------------------------------------------------------------
-- One row per booking, for a resident's own car or for a guest. The resident
-- who booked ('host') stays accountable either way.
--
-- A booking's life: held -> parked -> ended, with cancelled and expired as the
-- other endings. `state` is where it is now; `close_reason` records why it
-- stopped, which is what later questions ("how many were actually used?") need.
CREATE TABLE booking (
    id                INTEGER PRIMARY KEY,
    space_id          INTEGER NOT NULL REFERENCES space(id),
    host_person_id    INTEGER NOT NULL REFERENCES person(id),
    kind              TEXT NOT NULL CHECK (kind IN ('self', 'guest')),

    guest_label       TEXT,                     -- 'Mum': who the space is for
    guest_phone       TEXT,                     -- so the owner can reach whoever parked
    -- The guest link is a password: whoever holds it can act on this booking.
    -- Only the SHA-256 fingerprint of the link is stored, so a stolen copy of
    -- this file cannot be turned back into working links. The host sees the
    -- link once; "get a new link" replaces this fingerprint.
    guest_token_hash  TEXT UNIQUE,

    plate             TEXT,                     -- copied at booking time, so later edits don't rewrite history
    start_utc         TEXT NOT NULL,
    end_utc           TEXT NOT NULL,

    state             TEXT NOT NULL
                      CHECK (state IN ('held', 'parked', 'ended', 'cancelled', 'expired')),
    claimed_by        TEXT CHECK (claimed_by IS NULL OR claimed_by IN ('parker', 'host')),
    claimed_at_utc    TEXT,
    closed_at_utc     TEXT,                     -- when it stopped being held or parked
    close_reason      TEXT CHECK (close_reason IS NULL OR close_reason IN
                          ('ended', 'released', 'cancelled', 'reclaimed',
                           'withdrawn', 'expired', 'occupied')),
    created_at_utc    TEXT NOT NULL,

    CHECK (end_utc > start_utc),
    -- A guest booking must say who it is for, before any link is made.
    CHECK (kind = 'self' OR guest_label IS NOT NULL)
);
-- The index that matters: "is this space free between these two moments?" reads
-- only the rows for that space and state, instead of every booking ever made.
CREATE INDEX booking_by_space_window ON booking(space_id, state, start_utc, end_utc);
CREATE INDEX booking_by_host         ON booking(host_person_id, state);


-- The record -----------------------------------------------------------------
-- Append-only: rows are added, never changed or removed. This is the app's
-- memory, and version 2's rules will be based on it. `detail` holds whatever
-- else that kind of event needs, as JSON text.
CREATE TABLE event (
    id               INTEGER PRIMARY KEY,
    at_utc           TEXT NOT NULL,
    type             TEXT NOT NULL,             -- 'booking.created', 'right.assigned', ...
    space_id         INTEGER REFERENCES space(id),
    booking_id       INTEGER REFERENCES booking(id),
    actor_person_id  INTEGER REFERENCES person(id),
    actor_kind       TEXT NOT NULL
                     CHECK (actor_kind IN ('person', 'guest', 'coordinator', 'maintainer', 'system')),
    detail           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX event_by_time    ON event(at_utc);
CREATE INDEX event_by_booking ON event(booking_id);
CREATE INDEX event_by_type    ON event(type, at_utc);


-- Signing in -----------------------------------------------------------------
-- A session is a signed-in phone. Only a fingerprint of the cookie is stored:
-- if this file leaked, nobody could use it to sign in as a resident. The same
-- reasoning as never storing passwords.
CREATE TABLE session (
    id                INTEGER PRIMARY KEY,
    token_hash        TEXT NOT NULL UNIQUE,
    person_id         INTEGER NOT NULL REFERENCES person(id),
    expires_at_utc    TEXT NOT NULL,
    last_seen_at_utc  TEXT NOT NULL,
    user_agent        TEXT,                     -- so a person can recognise their own devices
    created_at_utc    TEXT NOT NULL
);
CREATE INDEX session_by_person ON session(person_id);

-- One-time codes for signing in on a new phone, or after losing one. Hashed for
-- the same reason, with an attempt count so a code can't be guessed.
CREATE TABLE login_code (
    id              INTEGER PRIMARY KEY,
    code_hash       TEXT NOT NULL UNIQUE,
    person_id       INTEGER NOT NULL REFERENCES person(id),
    purpose         TEXT NOT NULL CHECK (purpose IN ('invite', 'device')),
    expires_at_utc  TEXT NOT NULL,
    used_at_utc     TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at_utc  TEXT NOT NULL
);


-- Notifications --------------------------------------------------------------
-- One row per phone that agreed to receive notifications. A person may have
-- several (phone, tablet).
CREATE TABLE push_subscription (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES person(id),
    endpoint        TEXT NOT NULL UNIQUE,       -- the address the phone's maker gives us
    p256dh          TEXT NOT NULL,              -- keys that let only that phone read the message
    auth            TEXT NOT NULL,
    last_ok_at_utc  TEXT,
    created_at_utc  TEXT NOT NULL
);
CREATE INDEX push_subscription_by_person ON push_subscription(person_id);

-- Notifications waiting to be sent, or already sent. Writing the row in the
-- same transaction as the change it announces means a crash can't lose it: the
-- next sweep finds it still pending. `dedupe_key` is UNIQUE, so the same
-- reminder can never go out twice.
CREATE TABLE notification (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES person(id),
    booking_id      INTEGER REFERENCES booking(id),
    kind            TEXT NOT NULL,              -- 'booked', 'start', 'expiry', 'end', 'reclaim', 'notice', 'signup'
    dedupe_key      TEXT NOT NULL UNIQUE,
    payload         TEXT NOT NULL DEFAULT '{}',
    due_at_utc      TEXT NOT NULL,
    sent_at_utc     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'skipped', 'failed')),
    created_at_utc  TEXT NOT NULL
);
CREATE INDEX notification_pending ON notification(status, due_at_utc);


-- Odds and ends --------------------------------------------------------------
-- Small values that change while the app runs, such as the current sign-up
-- code. Settings that only a developer changes live in app/config.py instead.
CREATE TABLE setting (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at_utc  TEXT NOT NULL
);
