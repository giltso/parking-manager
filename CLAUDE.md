# Parking Manager

A parking-sharing web app for one residential building. This is a learning
project: the code is meant to be read and understood, not just run.

## Where things are documented

| File | Role | Updated when |
|---|---|---|
| The code | How the app actually works; the final word | Always, with its comments |
| QUESTIONS.md | Open problems that need someone else's input, in plain language. Created once the client has replied to the suggestion doc, starting with whatever is still unanswered. | A question comes up or gets answered |
| PLAN.md | Design reference from before implementation: data model, screens, edge cases, build order | A design choice changes (behaviour, data, rules), not for code-level details |
| PARKING_MANAGER_SUGGESTION.md | Record of the plain-language plan sent to the client for approval. Kept accurate as a record; will be removed eventually. | Only to fix a mistake, and to add an "Approved on [date]" line at the top once approved |
| README.md | The public front page: what the project is, how to run it | Setup or run steps change |

Update this table whenever a file is added, renamed, moved or changes role.

## Rules

1. **Explain the plan before changing anything.**
   State what you intend to do and why, then wait for a green light, not a
   summary after the fact. Reading and searching need no approval. Editing,
   committing and pushing do. If the plan changes partway through, stop and ask again.

2. **Document the code thoroughly, in teaching language.**
   The code is read by someone learning. Every file opens with a comment that
   explains what it's for and how it fits with the rest. Every function says what
   it does, what it takes, what it returns, and why it exists. Inline comments
   explain each meaningful step. The first time a file uses a Python or web
   concept (a transaction, a decorator, a cookie), explain it in plain words.
   Tricky logic (availability rules, best fit, time zones) gets line-by-line comments.

3. **Comments describe the current system, not the change that produced it.**
   No "just changed", no "now X", no "X today, Y later". Comments in that voice
   were accurate once and then decay with no edit to the code above them. Keep
   history only where it explains why a boundary exists. Everything else
   belongs in the commit message. Update comments in the same change as the
   code they describe.
   Notes about unfinished work (TODOs, placeholders) must be accurate and
   complete: what is missing, why, and where it's tracked (a QUESTIONS.md entry
   or a PLAN.md section).

4. **QUESTIONS.md is how we talk to non-technical people.**
   When work needs someone else's input, add an entry in plain language. Each
   entry says who should answer, why it matters, and its status, and links to
   the PLAN.md section or code it affects. Once answered, record the answer and
   the date, then update the code or PLAN.md to match.

5. **The repository is public.**
   Never commit secrets (notification keys, `.env` files), the database file, or
   real residents' names and phone numbers.

6. **Git: one topic per commit.** Never rewrite history or force-push without asking.
