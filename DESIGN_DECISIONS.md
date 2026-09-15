# Design Decisions

**Project:** Parking sharing app for one residential building (~100 apartments)
**Status:** Before development. Nothing is built, and nothing is confirmed yet.
**Last updated:** 2026-09-15

The technical version is [PLAN.md](PLAN.md).

## How this page is ordered

Items are ordered by **weight**: how hard they'd be to change later, and how much
they shape the way people use the app. The heaviest come first.

| Tier | What changing it would mean |
|---|---|
| **Foundations** | Rebuilding most of the app, or asking every resident to start over |
| **Structure** | Reworking several screens and parts of the data |
| **Details** | A small change: one role, a few buttons, a setting |

Each item carries one tag:

| Tag | Meaning |
|---|---|
| **Core idea** | Part of the original concept; the app is designed around it |
| **Default** | What the app will do unless the project owner decides otherwise |
| **Open** | No default yet; needs the project owner's input |

**Words used on this page**
- **User:** someone registered permanently with the app (a resident). A user can be a
  **solicitor** (has a space and offers it), a **client** (has a car and books
  spaces), or both.
- **Guest:** a visitor with no account, who uses a link a client sent them.

## At a glance

| # | Item | Tag | Cost to change later |
|---|---|---|---|
| **Foundations** | | | |
| Q1 | What kind of app it is, and its web address | Core idea | Complete rebuild; a new address after launch means every resident reinstalls |
| Q2 | Architecture: one program, one database file | Default | Moving to an online database or a bigger stack means reworking storage, background jobs and deployment |
| C1 | Solicitors do nothing extra; clients carry the cost | Core idea | Redesign every screen |
| C2 | Users, guests and accountability | Core idea | Redo accounts, links and every booking flow |
| C3 | Availability: closed unless opened | Core idea | Redo the data model, owner screens and search |
| C4 | A booking's life: claim it or lose it | Core idea | Redo booking states, reminders and history |
| **Structure** | | | |
| C5 | Finding and booking: explicit, instant, best fit | Core idea | Rework search and booking screens |
| Q3 | How owners open and block their space | Default | Rework the owner's screens and how openings are stored |
| Q4 | Reclaiming a space | Open | Rework booking states and notifications |
| Q5 | Languages | Default | Adding a language late touches every screen |
| Q6 | Shabbat and holidays | Open | Adds an exception to the booking life (C4) |
| Q7 | Registration and sign-in | Default | Rework sign-up and sign-in screens |
| Q8 | Owning a space | Default | Rework ownership data and dispute handling |
| **Details** | | | |
| Q9 | Who runs the app | Default | Split or merge one small role |
| Q10 | Helper features | Default | Add or remove a feature |
| Q11 | Timings | Default | Change a setting, no new code |
---

# Foundations

## Q1. What kind of app is it, and its web address
**Core idea** · Cost to change: complete rebuild; a new address after launch means every resident reinstalls

**Defaults to:** A website that installs to the phone's home screen and works like
an app, with no App Store. **Phone notifications are the only channel**, with no
SMS or email.

**Why:** It's one version for iPhone and Android, with no App Store approval and
no monthly messaging costs. Guests need nothing installed.

**Trade-off:** On iPhone, notifications only work after "Add to Home Screen", and
notification buttons aren't shown, so actions take two taps. The app shows iPhone
users a short guide.

**The web address is part of this choice.** The installed app and its notification
permission are tied to the address. Testing can use a temporary address, but
**before v1** the building needs its own domain (about $10–15 a year). After
launch it must never change, or every resident has to reinstall and turn
notifications back on. Testers reinstall once, when the real domain arrives.

**To decide:**
- Is iPhone's extra step acceptable for residents? A native app, or adding SMS,
  would mean a different project.
- A domain name. Is there a building or street name to use?

## Q2. Architecture: one program, one database file
**Default** · Cost to change: moving to an online database or a bigger stack means reworking storage, background jobs and deployment

**Defaults to:** The simplest setup that serves one building well:
- **One program** runs everything: pages, booking logic, reminders and notifications.
- **One database file** sits next to it on the same machine. There's no online
  database service and no separate database server.
- **Pages are built on the server** and sent to the phone, with no separate
  app framework to maintain.

**Why:** For ~100 apartments this is plenty fast. There's nothing extra to pay for
or keep running, and backing up means copying one file. It's also the easiest
setup for a beginner to understand and fix.

**When it would have to change:**
- Serving **several buildings** from one app.
- Needing the app to **stay up even if one machine fails**, which needs more than
  one server and therefore an online database.
- Letting **other systems** (for example building management software) read or
  write the data directly.

**What stays easy:** Moving the whole app to another machine means copying one
file, so going from a home computer to a rented server doesn't count as an
architecture change. All database access is also kept in one layer of the code,
so a later switch to an online database wouldn't touch the screens or the
booking rules. It would still be real work.

**Cost of starting on a home computer:** The app is unreachable whenever that
computer is off or asleep. Bookings catch up correctly when it's back, but
reminders due during the outage are skipped.

**To decide:** Could this ever serve more than one building, or need to stay up
through a machine failure? If either is likely, it's cheaper to choose an online
database now than to switch later.

## C1. Solicitors do nothing extra; clients carry the cost
**Core idea** · Cost to change: redesign every screen

A solicitor gains nothing from lending a space. The first time the app annoys
them, they stop offering it, and without spaces the app is useless. A client
*needs* a space and will put up with extra steps. So whenever a choice trades
one side's convenience against the other's, the solicitor gets the easy side.

| Solicitor | Client |
|---|---|
| One question to get started: "Is your car usually here or usually away?" | Must give an exact start **and** end for every booking |
| One tap to block or open their space, never a form (walkthrough: Q3) | Must tap "I'm parked" on arrival, or lose the booking |
| Never asked to approve, reply or wait for anything | Extends, releases and rebooks themselves |
| Gets exactly one notification: "your space was booked" (for information only) | Gets the reminders and does the follow-up |
| Can take the space back (exact rules: Q4) | Accepts that they may be bumped |

## C2. Users, guests and accountability
**Core idea** · Cost to change: redo accounts, links and every booking flow

- A **user** is registered permanently. They act as a **solicitor** (offering a
  space), a **client** (booking one), or both. For example, an owner with two
  cars books a second space like anyone else.
- A **guest** has no account. The client books for them and sends a link. The
  guest's page shows the space, the times and one button: **I'm parked**.
  The link stops working when the booking ends.
- **The client who booked is always accountable**, including for their guest.
  A guest name ("Mum") is required. If the guest can't tap the button, the client
  can confirm for them, but only from the start time. The record shows who confirmed.
- **Disputes are mutual.** A solicitor always sees who booked their space: the
  client's name, phone and plate, and the guest's phone. In a dispute (a
  reclaim, or a space found occupied), everyone involved sees each other's
  phone. A guest must give a phone number before tapping "I'm parked".
  Solicitors are told this when they claim a space. The public list of spaces
  never shows phone numbers.
- Licence plates are optional. A user can save several.

**Why mutual:** Whoever's car is in the space must be reachable directly, and it
has to work both ways. A guest who misbehaves can be told off by the owner, and a
guest who is bumped can reach the owner.

## C3. Availability: closed unless opened, the most specific rule wins
**Core idea** · Cost to change: redo the data model, owner screens and search

- A space is **closed** unless its solicitor opens it.
- Solicitors use two kinds of rule, each of which can open or close time:
  - **Recurring:** "available every Tuesday 08:00–18:00"
  - **One-time:** "available 15–27 March 2027"
- When rules overlap:
  1. A one-time rule beats a recurring one.
  2. Otherwise, the rule covering less time overall wins.
  3. If it's still a tie, *closed* wins.

  *Example:* "open all week" plus "closed Saturdays" means closed on Saturdays.
  A narrower rule is almost always the owner's more deliberate instruction, and
  when in doubt, keeping the space closed protects the owner.
- **How far ahead** (the exact numbers are in Q11):

  | Kind of opening | Bookable |
  |---|---|
  | One-time | Can be created any time ahead; bookable within the next **14 days** |
  | Recurring | Only the next **7 days** appear, and only they can be booked |

  A recurring schedule may have been set long ago and forgotten, so it only
  reaches a week ahead. A one-time opening is a recent, deliberate choice.
- Recurring times follow the building's clock through summer and winter time.

## C4. A booking's life: claim it or lose it, every change on the record
**Core idea** · Cost to change: redo booking states, reminders and history

- A new booking is **reserved**. On arrival, someone taps **I'm parked**. If nobody
  does within the grace period after the start (Q11), the booking **expires**
  and the remaining time returns to the pool. This is the only thing the app
  cancels by itself. Without it, reservations nobody uses would block spaces for everyone.
- **No early confirmation.** Arrived early? Move the start earlier ("start
  now") if the space is free. Parked but forgot to tap? Tapping later, before
  expiry, is fine.
- **Before parking**, start and end can be moved earlier or later if the space is
  free. **After parking**, only the end can change: extend, if the space is still free.
- Reminders go to the client (for guest bookings, to the client who booked):
  at the start, before expiry, and before the end.
- **Everything is on the record.** Every booking, confirmation, change, expiry,
  cancellation, reclaim and search is saved with a timestamp. Searches that
  found nothing show how much demand goes unmet. The solicitor and the
  coordinators (Q9) see a booking's change history. Bookings whose start was
  pushed back repeatedly, or that ended up unused, show up in a report.
  Moving a start later is useful, but it could be abused to hold a space without
  using it. Making it visible keeps people honest now and gives v2 the data to
  set limits if needed.
- **No limits or penalties in version 1.** The recorded data will decide v2 rules.
  The booking logic is kept in one place, so credits or payments can be added
  later.

---

# Structure

## C5. Finding and booking: explicit, instant, best fit
**Core idea** · Cost to change: rework search and booking screens

- The main screen has two buttons: **For me** and **For a guest**.
- The client gives a start (default: now) and an end (required; default: the
  rest of today, or tomorrow 08:00 if it's late evening). There are no open-ended
  bookings, because a booking with no end would lock a solicitor's space indefinitely.
- Any open, unbooked space can be booked, with no connection to it needed.
  Booking is **instant**, with no approval, and the client sees the space number
  immediately, before going down or before the guest arrives.
- **Best fit:** the app offers the space whose free time fits the request most
  tightly, and never one that would leave a leftover gap too short to be useful
  (the minimum gap is Q11).

  *Example:* a client needs 14:00–17:00. A space free exactly 14:00–17:00 is
  offered first. A space free until 17:30 would leave a useless 30 minutes, so
  it isn't offered.

  It works like packing boxes onto shelves: short requests fill short gaps, and
  long free periods stay available for long requests.

## Q3. How owners open and block their space
**Default** · Cost to change: rework the owner's screens and how openings are stored

C1 says owners should hardly be bothered. This item shows what that means in
practice for two very different owners.

### The owner's screen
Each space has one screen for its owner:
- **Status** in large text: *Open*, *Closed*, or *Booked by Dana (apt 7) until 18:00*.
- **This week** as a strip, showing open, closed and booked time.
- **One row of buttons**, which changes with the status:
  - When open: **Block** → *next 3 hours · rest of today · until tomorrow 08:00 · until I undo it*
  - When closed: **Open** → *rest of today · until tomorrow 08:00 · until I close it*
- Tapping any opening or block on the strip shows **Remove**, one tap.
- **Trip** (pick two dates) and **Schedule** (a weekly routine) sit behind a small
  link, for owners who want them.

The owner never needs to know how rules combine (C3). Whatever they tapped last
is what the screen shows.

### Two owners

| | Owner A: needs the space most days | Owner B: rarely uses the space |
|---|---|---|
| **Starting answer** | "Usually here" | "Usually away" |
| **What that sets up** | Nothing. The space stays closed. | One recurring opening: every day, all day |
| **An ordinary week** | Nothing to do | Nothing to do |
| **Out for the evening** | One tap: *Open → rest of today* | Nothing to do (already open) |
| **Away on a trip** | *Trip*: pick two dates, once | Nothing to do |
| **Away on a routine** (e.g. at work weekdays 08:00–18:00) | *Schedule*: set once, then nothing | Nothing to do |
| **Needs the space** | Nothing to do (already closed) | One tap: *Block → rest of today* (or another duration) |
| **Changed their mind** | One tap: *Remove* | One tap: *Remove* |
| **Situation changes for good** (new car, car sold) | One tap to switch to "usually away" | One tap to switch to "usually here" |
| **Notifications** | "Your space was booked", only after opening it | "Your space was booked" |

Both owners' starting answers match their normal week, so **doing nothing is
always correct**. They only act for exceptions, and almost every exception is
one tap. The only multi-step action is picking trip dates, and that's something
an owner chooses to do in order to share more.

If a block would cover someone's booking, the button says so before it's
tapped. What happens next is Q4.

### When an owner forgets
- **Owner A forgets to open:** the space stays closed. Nobody is harmed; the
  building just misses a free space.
- **Owner B forgets to block and parks in their own open space:** a client may
  book it and find it taken. Three things limit this:
  - A recurring opening only reaches **7 days ahead** (C3), so an old "usually
    away" setting can't collect bookings weeks in advance.
  - Owner B is told whenever the space is booked, so a booking at a time they'll be home is a
    prompt to tap *Block*.
  - The client has the "space is occupied" button (Q10) and gets another space.

**To decide:**
- Are these the right durations? Add *until after Shabbat*?
- Is picking dates for a trip acceptable, or should there be quick options such
  as *this weekend* or *next 7 days*?
- If an owner keeps opening the same times (every Tuesday, say), should the app
  **offer** to turn it into a schedule? This would be an in-app suggestion only,
  never a notification.

## Q4. Reclaiming a space
**Open** (for the project owner) · Cost to change: rework booking states and notifications

**Core idea:** An owner can always take their space back, immediately, with no
reason needed. A booking in the way is cancelled, and both sides see each
other's phone.

**Why it's open:** Reclaiming is where owner convenience and client reliability
collide most, for example when a guest has already parked and driven away.

**Starting point for discussion:** Instant for bookings not yet parked, a short
notice time for parked cars, and every reclaim recorded.

**To decide:**
- Is it instant even when a car is already parked, or does a parked car get
  notice time (e.g. 30–60 minutes)?
- Can owners cancel *future* bookings right up to their start?
- Should repeated reclaims by one owner be visible to anyone?

## Q5. Languages
**Default** · Cost to change: adding a language late touches every screen

**Defaults to:** English and Hebrew, chosen per user. Hebrew screens are
right-to-left, and notifications arrive in each person's own language. The guest
page follows the guest's phone language and has a switch. Phone numbers and
plates always display left-to-right, so they never appear scrambled inside Hebrew text.

**Why it's heavy:** Right-to-left layout and two sets of text have to be built in
from the start. Adding a language later means going back through every screen.

**To decide:** Are any other languages common in the building (for example
Russian, Arabic or French)?

## Q6. Shabbat and holidays
**Open** · Cost to change: adds an exception to the booking life (C4)

**Problem:** Some residents and guests don't use phones on Shabbat or holidays.
They can't tap "I'm parked", so their booking would expire (C4).

**Starting suggestion:** A "no confirmation needed" option when booking, allowed
only if the booking starts on Shabbat or a holiday. It skips the expiry, the
solicitor can see it, and it's recorded.

**To decide:** Is this the right approach? Does it apply to both guests and
residents? Which holidays count?

## Q7. Registration and sign-in
**Default** · Cost to change: rework sign-up and sign-in screens

**Defaults to:** A sign-up link is shared in the building's WhatsApp group. A
resident enters name, phone, apartment and language, then waits for a
coordinator to approve them. There are no passwords: a phone stays signed in for
months, a new device is added with a code shown on an existing device, and
anyone who lost their phone gets a sign-in link from a coordinator.

**Why:** Adding every resident by hand would slow the launch. Approval keeps
outsiders out even if the link is forwarded. Passwords get forgotten, and
resetting them would need email or SMS, which the app doesn't use (Q1).

**Cost:** Coordinators have to approve sign-ups promptly. That work falls on
coordinators, never on solicitors.

**To decide:** Is coordinator approval the right gate? Is a sign-in link from a
coordinator acceptable for lost phones?

## Q8. Owning a space
**Default** · Cost to change: rework ownership data and dispute handling

**Defaults to:**
- A coordinator enters the space numbers once, exactly as painted on the floor.
- A user claims an unclaimed space instantly. All claims, including past ones,
  are listed publicly.
- An owner can add a **co-owner** (full control) or a **manager** (a stand-in
  while away, optionally until a set date). A manager can do everything an owner
  can except add or remove people. Only a coordinator can remove a co-owner.
- A claim on an already-owned space becomes **disputed**. A coordinator checks
  it by hand and decides: add as co-owner, replace the owner, or reject.
  Meanwhile the current owner keeps control and isn't asked anything.
- The original concept's space-level "user" role is removed, because "user" now
  means a registered person (C2). Anyone who parks in a space by private
  arrangement is either outside the app or added as a manager.

**Why:** Honest owners never wait, and a false claim is visible to the whole
building. Contested ownership needs a person who can check the facts, not a race
to click first. Letting only coordinators remove co-owners stops one co-owner
from locking out another.

**To decide:**
- Should claiming an unclaimed space also need a coordinator's approval, or is
  public visibility enough?
- Should managers also get "your space was booked" while standing in for the owner?

---

# Details

## Q9. Who runs the app
**Default** · Cost to change: split or merge one small role

**Defaults to:** Two separate roles.

| | Coordinator | Maintainer |
|---|---|---|
| **Works** | Inside the app | Outside the app |
| **Does** | Enters space numbers, approves sign-ups, settles disputed claims, sends sign-in links, removes users, sees reports, appoints other coordinators | Writes and updates the code, runs the server, database, backups and domain |
| **Special powers in the app** | Yes, and every action is recorded and visible to the other coordinators | **None.** Their own account is an ordinary user. |

The separation also holds **in practice**:
- The maintainer fixes data only through **recorded maintenance commands**,
  never by editing the database by hand. Every fix appears in the same record
  coordinators see.
- Every code change is kept in a version history.
- During testing, one person may hold both roles. **Before v1 they are separated.**
- If no coordinator can be reached in an emergency, the maintainer uses a
  recorded maintenance command.

At launch the coordinators would be the project owner, the building manager and
the tenant leader. The maintainer would be the developer, with no coordinator
powers. It's called "coordinator", not "manager", because "manager" already
means an owner's stand-in (Q8).

**Why:** The person who can change how the app works shouldn't also be the one
settling disputes between neighbours. Separating the roles builds trust, and the
building keeps running if either person is unavailable.

**Cost:** At least one active coordinator is needed besides the maintainer. The
maintainer can still technically reach the database, so the separation relies on
recording everything, not on a hard wall.

**To decide:** The split and the people.

## Q10. Helper features
**Default** · Cost to change: add or remove a feature

**Defaults to:** both of these are included.
- **Longer-booking suggestion.** If every free space would leave a useless gap,
  offer a slightly longer booking that closes it ("Space 12 fits if you book until 17:30").
- **"Space is occupied" button.** If a client or guest finds another car in their
  space (for example the owner came home and forgot to block it), one tap shows
  the phones involved and books the next best space. Every report is recorded,
  which shows which spaces are unreliable.

**To decide:** Include both, one, or neither?

## Q11. Timings
**Default** · Cost to change: change a setting, no new code

**Defaults to:**
- **Grace period** before an unclaimed booking expires: **60 minutes** after start.
- **Minimum leftover gap** that best fit may leave: **60 minutes**.
- **Reminders:** at the start, 10 minutes before expiry, 15 minutes before the end.
- **Extend button** adds 1 hour.
- **Booking horizon:** 14 days (recurring openings: 7).

**To decide:** Keep these for testing and adjust after real use?
