# Parking Manager Suggestion

A plain-language walk through the plan for the building's parking-sharing app:
what it does, why each choice was made, how some choices changed along the way,
and which questions are still open.

**Status:** Nothing is built yet. Everything here is the current plan and can
change. The technical version is [PLAN.md](PLAN.md), in the same order.

**Why keep this:** once the app runs, we'll compare what happened with what we
expected. Writing the reasons down now lets us tell later whether a choice was
wrong, or whether the reason behind it no longer applies.

**Words used here**
- **Owner:** a resident who has a parking space and may lend it.
- **Client:** a resident who books a space, for their own car or for a guest.
- **Guest:** a visitor with no account, using a link from the client who booked.
- **Coordinator:** a trusted person who runs the building's side (approvals, disputes).
- **Maintainer:** the person who builds and runs the program itself.

## 1. The idea

About 100 apartments share one car park. Most residents already have a space or
a private arrangement, so free spaces are common but come at irregular times.
Demand is occasional and comes from two places: a resident needs a space for a
**visiting guest**, or has **more cars than spaces**.

**The rule that shapes everything:** owners gain nothing from lending a space, so
they'll quit the moment the app annoys them. Clients *need* a space and will put
up with effort. So owners get defaults, one-tap actions and almost no obligations, and
clients give exact times, confirm arrival, and extend or rebook themselves.

Version 1 has no fees, limits, ratings or penalties. Instead, everything is
recorded, so later rules can be based on how people really behaved.

**Open questions**
- What counts as success after three months: bookings made, owners sharing, or
  fewer parking arguments?

## 2. What kind of app it is and how it's built

**The plan for Version 1**
- A **website that installs to the phone's home screen**, with no App Store.
- **Phone notifications** are the only channel. No SMS, no email.
- **One program and one database file** on a single machine.
- **English and Hebrew**, chosen per person. Hebrew reads right to left.
- A **home computer for testing**, then a rented server, under the building's
  **own web address** from launch.

**Why**
- One version works on iPhone and Android, with no store approval, and guests
  just open a link.
- SMS and email cost money every month and need outside accounts.
- For one building, one program and one file is plenty. It's cheap, easy to back
  up, and simple enough for a beginner to fix.
- Right-to-left layout has to be built in from day one. Adding it later would
  mean revisiting every screen.
- The installed app is tied to its web address. Changing the address after
  launch would force every resident to reinstall.

**Trade-offs we accepted**
- On iPhone, notifications need "Add to Home Screen", and buttons inside
  notifications aren't shown, so some actions take two taps.
- On a home computer, the app is down whenever that computer is off.
- Moving to an online database later (several buildings, or surviving a machine
  failure) would mean reworking storage and setup, though not the screens or rules.

**How we got here:** Hosting started open. It became a home computer now and a
server later, then "a domain is required before version 1 but not for testing".
We also separated where the app runs (cheap to change) from how it's built
(expensive to change).

**Open questions**
- Is the iPhone extra step acceptable for residents?
- What should the web address (domain) be called?
- Are any other languages common in the building?

## 3. What the app keeps track of

- **People:** name, phone, apartment (display only), language, approved or not.
- **Licence plates:** optional; a person can have several.
- **Spaces:** the numbers painted on the floor, entered once by a coordinator.
- **Who holds a space:** **owners** (including co-owners) and **managers**, who
  stand in while an owner is away.
- **Openings and blocks**, **bookings**, and **the record** of every action.

**Why:** Nothing is truly deleted. Old claims, removed openings and cancelled
bookings stay in the history, so neighbours can spot a false claim and we get
real data later.

## 4. When is a space available?

**The plan**
- A space is **closed** unless its owner opens it.
- Owners open or close time in two ways. **Recurring:** "every Tuesday
  08:00–18:00", or "usually away". **One-time:** "tonight", or "15–27 March".
- When they overlap, the more specific one wins. One-time beats recurring,
  otherwise the one covering less time wins, and a tie means closed. *Example:*
  "open all week" plus "closed Saturdays" means closed on Saturdays.
- **How far ahead:** bookings up to 14 days ahead. Recurring openings only reach
  7 days ahead. One-time openings can be created any time and become bookable
  within 14 days.
- Owners never need to learn these rules: **whatever they tapped last is what
  their screen shows**.
- Bookings are stored as exact moments. Schedules use the building's clock, so
  "08:00" stays 08:00 through summer and winter time.

**Why:** Closed by default means no space is shared by accident. The more
specific rule is almost always the more deliberate one. Recurring openings are
kept to a week because an owner who chose "usually away" months ago may have
forgotten, and shouldn't find bookings weeks out.

## 5. Finding a space

**The plan**
- Two buttons: **For me** and **For a guest**.
- Start defaults to now. End is required and defaults to the rest of today, or
  tomorrow 08:00 if it's late evening.
- The app offers the space whose free time **fits the request most tightly**, and
  never one that would leave a leftover gap under 60 minutes.
- If no space fits, it suggests the space that would fit with the smallest change
  to the times ("Space 12 fits if you book until 17:30").
- Booking is **instant**. If two people tap the same space at once, the first
  gets it and the second is shown the next best.

**Why:** It's like packing a shelf: short requests fill short gaps, so long free
periods stay available for people who need them, and tiny leftovers help no one.
Instant booking means the client knows the space number before going down.

**Open questions**
- Is 60 minutes the right minimum gap?
- Should this "smallest change" suggestion be in version 1?

## 6. A booking's life

**The plan**
- A new booking is **reserved**. On arrival, someone taps **I'm parked**.
- If nobody taps it within **60 minutes after the start**, it **expires** and the
  rest of its time returns to the pool. This is the only automatic cancellation.
- **No early confirmation.** Someone arriving early can move the start to "now" if the space
  is free. Parking first and tapping later, before expiry, is fine.
- **Before parking**, start and end can move if the space is free. **After
  parking**, only the end can change, by extending if the space is still free.
- Every booking ends as **used** (ended or released) or **not used**
  (cancelled, expired or reclaimed), so "how many bookings were real?" is easy to answer.
- A background check runs every 30 seconds. After downtime it catches up with the
  correct times.

**Why:** Without expiry, forgotten reservations would block spaces. Confirming
before the start could clash with the previous booking. Changes are allowed but
visible: a start pushed back again and again shows up in a report.

**How we got here:** "Confirm early" was replaced by "move your booking earlier".
Moving the start later was allowed on condition that every change stays visible
in the record.

**Open questions**
- **Shabbat and holidays:** people who don't use phones can't tap "I'm parked",
  so their booking would expire. Starting suggestion: a "no confirmation needed"
  option, only for bookings starting on Shabbat or a holiday. Right approach?
  Which holidays count?
- Are the timings right: 60 minutes to confirm, and reminders at the start, 10
  minutes before expiry and 15 minutes before the end?

## 7. The owner's side

**Getting started:** claim a space and answer one question, "Is your car usually
here or usually away?" *Here* keeps the space closed; *away* opens it all week.

**The owner's screen:** the status (open, closed, or who booked it), this week at
a glance, and one row of buttons.
- When open: **Block** → *next 3 hours · rest of today · until tomorrow 08:00 · until I undo it*
- When closed: **Open** → *rest of today · until tomorrow 08:00 · until I close it*
- **Trip** (two dates) and **Schedule** (a weekly routine) sit behind a small link.

| | Needs the space most days | Rarely uses the space |
|---|---|---|
| Starts with | "Usually here" | "Usually away" |
| Ordinary week | Nothing to do | Nothing to do |
| Out for the evening | One tap to open | Nothing to do |
| Away on a trip | Pick two dates once | Nothing to do |
| Needs the space | Nothing to do | One tap to block |
| Forgets | Space stays closed; nobody is harmed | Someone may book it |

For both, doing nothing is usually correct. An owner who forgets to block is
covered three ways: recurring openings only reach a week ahead, the owner is
told whenever the space is booked, and a client who finds the space taken has a
"space occupied" button that finds another space.

**Taking the space back:** blocking booked time warns first ("rest of today,
cancels Dana's booking"), then cancels that booking. Both sides see each other's phone.

**Sharing control:** an owner can add a co-owner or a manager. Only a
coordinator can remove a co-owner, so one co-owner can't lock out the other. A
claim on an already-owned space goes to a coordinator. Meanwhile the owner isn't
asked anything.

**Phones and obligations:** owners always see who booked, including the guest's
phone. In a dispute, everyone involved sees each other's number. The public list
shows no phones. Owners are never asked to approve, reply or wait. Their only
notification is "your space was booked".

**How we got here:** Co-owners and coordinator-handled disputes were added. Phone
sharing started one-way (guests couldn't see the owner's number). It became
mutual, because owners must be able to reach a misbehaving guest, and a bumped
guest must be able to reach the owner.

**Open questions**
- **Reclaiming (needs the client):** is it instant even if a car is parked, or
  does a parked car get notice time? Can future bookings be cancelled right up to
  their start? Should repeated reclaims be visible?
- Are the block and open durations right? Add "until after Shabbat"?
- Is picking trip dates acceptable, or add quick options like "this weekend"?
- Should managers also get "your space was booked"?
- Should claiming an unclaimed space need a coordinator's approval?

## 8. Guests

**The plan**
- The client books "for a guest", gives a guest name ("Mum"), and sends the link
  through any messaging app.
- The guest's page shows the space, the times, the client's name and phone, and
  one button: **I'm parked**. The guest enters a phone number first, unless the
  client already did.
- Early guests see "Start now" if the space is free. Parked guests see Release
  and Extend.
- The client can confirm for the guest, but only from the start time. The record
  shows who confirmed.
- The link stops working when the booking ends. A messaging app's link preview
  can't press anything.

**Why:** Guests shouldn't have to register or install anything. The client stays
accountable, and the guest's number means the owner can reach whoever's car is in
the space.

## 9. Notifications

| When | Who | Buttons |
|---|---|---|
| A space is booked | Its owners (and managers) | none |
| Booking starts, not yet parked | The client | I'm parked · Release |
| 10 minutes before expiry | The client | I'm parked |
| 15 minutes before the end | The client | Extend |
| An owner takes the space back | The client, with the owner's phone | Call · Find another |
| Someone signs up, or a claim is disputed | Coordinators | none |

For guest bookings these go to the client who booked, and the guest sees the same
buttons on their page. Each person gets notifications in their own language.
Out-of-date reminders are skipped, and nobody gets the same one twice.

## 10. Signing in and who runs the app

**The plan**
- A sign-up link is shared in the building's group chat, and new residents wait
  for a coordinator's approval.
- No passwords. A phone stays signed in for months. A new phone is added with a
  code shown on an existing one. A lost phone means a coordinator sends a sign-in link.
- **Coordinators** work inside the app: approvals, disputes, sign-in links,
  reports. **The maintainer** works outside it (code, server, backups) and has no
  special powers inside. Every maintenance fix is recorded where coordinators can see it.
- Planned for launch: the project owner, the building manager and the tenant
  leader as coordinators; the developer as maintainer.

**Why:** Passwords get forgotten, and resets need email or SMS. Approval keeps
outsiders out even if the link spreads. The person who can change the app
shouldn't also be the one settling disputes between neighbours.

**How we got here:** A single "admin" was split into coordinator and maintainer,
with the separation meant to hold in practice, not just on paper.

**Open questions**
- Is coordinator approval the right gate, and a coordinator-sent link the right
  fix for lost phones?

## 11. Built to learn from

**Recorded:** every booking, confirmation (and who confirmed), change, expiry,
cancellation and reclaim, every opening, block and claim, and **every search,
including those that found nothing**. The booking rules live in one place, so
fees, credits or limits could be added later without rebuilding the screens.

**Questions to answer from the data after launch**
- How many searches found nothing, and when?
- How often do bookings expire unused, or have their start pushed back?
- How often do owners reclaim, and how far into a booking?
- Which spaces get "space occupied" reports?
- Do guests or clients confirm most arrivals?

## 12. When things go wrong

| Situation | What happens |
|---|---|
| Two people tap the same space at once | First gets it; second sees the next best |
| Guest arrives after expiry | Told it expired, shown the client's phone; client rebooks |
| Owner blocks booked time | Booking cancelled; both sides see phone numbers |
| Owner forgot to block, car in the space | Client taps "space occupied" and gets another space |
| Owner switches to "usually here" | Bookings in the newly closed time are cancelled |
| Last owner gives up a space | Space closes; its bookings are cancelled |
| Claim on an already-owned space | Goes to a coordinator; owner keeps control |
| App was off for an hour | Catches up with correct times; stale reminders skipped |
| Guest link forwarded to a stranger | Still works; the client is accountable and can cancel |
| Notifications turned off on a phone | App shows a banner to turn them back on |

## 13. How it will be built and checked

**Order:** version history and the base first, then availability rules, sign-in,
owners, finding and booking, the booking life, guests, notifications, coordinator
tools, and finally security and setup. Each step ends with something clickable.

**Checking:** during tests the app's clock can be set to any time, so "61 minutes
after the start" needs no waiting. The trickiest rules (overlapping openings,
clock changes, best fit) get the most tests.
