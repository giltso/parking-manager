# Parking Manager

A parking-sharing web app for one residential building. This is a learning
project: the code is meant to be read and understood, not just run.

## Where things are documented

| File | Role | Updated when |
|---|---|---|
| The code | How the app actually works; the final word | Always, with its comments |
| PLAN.md | Design reference from before implementation: data model, screens, edge cases, build order | A design choice changes (behaviour, data, rules), not for code-level details |
| PARKING_MANAGER_SUGGESTION.md | The whole plan in plain language, with the reasoning, the open points and the answers we get back. The version people outside the project read. | A decision is made or a question is answered |
| README.md | The public front page: what the project is, how to run it | Setup or run steps change |

Expect more documents as the project grows: notes on one area, a setup guide, a
record of a decision. Add each one to this table when you create it, with its
role and when it changes. If a document's job is already covered here, extend
the existing one instead of adding another.

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
   complete: what is missing, why, and where it's tracked (a PLAN.md section, or
   a section of the suggestion doc when it needs someone else's decision).

4. **Questions for other people go in the suggestion doc, in plain language.**
   When work needs someone else's input, write it there in the section it
   belongs to: what we need to know and why it matters. When the answer comes
   back, fold it into that section and update PLAN.md and the code to match, so
   the document always reads as the current plan rather than a list of debates.

5. **The repository is public.**
   Never commit secrets (notification keys, `.env` files), the database file, or
   real residents' names and phone numbers.

6. **Git: one topic per commit.** Never rewrite history or force-push without asking.
