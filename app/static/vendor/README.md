# Vendored libraries

Files in this folder were written by other people and are kept here on purpose,
rather than loaded from someone else's server at run time.

Why keep our own copy:
- the app has no outside dependency while it runs, so it works even if that
  server is down or blocked;
- nobody outside the building learns which residents opened the app, which they
  would if every page fetched a file from a third party;
- the exact file is in our version history, so an update is a visible change we
  chose, not something that happened overnight.

| File | Version | Source | Why it's here |
|---|---|---|---|
| `htmx.min.js` | 2.0.10 | https://cdnjs.cloudflare.com/ajax/libs/htmx/2.0.10/htmx.min.js | Lets a button update one part of a page without reloading it, so the app needs no JavaScript of its own |

htmx 4.0.0 exists. We stay on the 2.0 line for now because that is what the app
is written against; moving is a deliberate change with its own commit, after
reading what changed.

## Updating one of these

1. Download the new version into this folder.
2. Update the version and the address in the table above.
3. Run the tests, click through the screens that use it.
4. Commit the file and this table together, on their own.
