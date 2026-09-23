"""The shared plumbing every screen uses.

Three things belong to every request:

* the **database connection**, opened once when the app started;
* **who is asking**, worked out from the session cookie;
* the **language**, so text and page direction match the reader.

Routes ask for these by naming them as arguments. FastAPI notices the
`Depends(...)` marker and fills them in, which is why no route repeats this
work.

The same-origin check for forms also lives here, as the one door every change
passes through.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app import i18n
from app.clock import now_utc
from app.permissions import Actor, PermissionDenied
from app.services import auth

SESSION_COOKIE = "session"

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def db(request: Request) -> sqlite3.Connection:
    """The app's database connection."""
    return request.app.state.db


@dataclass(frozen=True)
class Viewer:
    """Everything a screen needs to know about the person in front of it.

    `person` is None for a visitor with no session. `actor` always exists: for a
    visitor it is simply one that may do nothing, so permission checks work the
    same way for everybody and no route has to handle "nobody" as a special case.
    """

    person: auth.Person | None
    actor: Actor
    language: str
    direction: str

    @property
    def signed_in(self) -> bool:
        return self.person is not None

    @property
    def waiting_for_approval(self) -> bool:
        return self.person is not None and self.person.status == "pending"


def viewer(request: Request) -> Viewer:
    """Work out who is asking, and in which language to answer.

    Language follows the person's own choice when they have one, then the
    cookie, then what their browser asks for, then the building's default.
    """
    connection = request.app.state.db
    person = auth.person_for_session(connection, request.cookies.get(SESSION_COOKIE))

    language = (
        person.locale if person
        else i18n.choose_language(
            cookie_value=request.cookies.get("lang"),
            accept_language=request.headers.get("accept-language"),
        )
    )

    return Viewer(
        person=person,
        actor=auth.actor_for(connection, person, now=now_utc()),
        language=language,
        direction=i18n.direction(language),
    )


# Short names, so routes read as `viewer: CurrentViewer` rather than repeating
# the `Annotated[..., Depends(...)]` spelling every time.
CurrentViewer = Annotated[Viewer, Depends(viewer)]
Database = Annotated[sqlite3.Connection, Depends(db)]


def require_signed_in(viewer: CurrentViewer) -> Viewer:
    """Refuse anyone without a session, for screens that assume a person."""
    if not viewer.signed_in:
        raise HTTPException(status_code=401, detail="sign in first")
    return viewer


SignedIn = Annotated[Viewer, Depends(require_signed_in)]


def render(request: Request, viewer: Viewer, template: str, **values):
    """Render a page with the things every template expects.

    Every template gets `t` for text, the language and direction, and the
    viewer, so the header can show who is signed in. Anything else is passed in
    by the route.
    """
    return templates.TemplateResponse(
        request,
        template,
        {
            "t": i18n.translator(viewer.language),
            "lang": viewer.language,
            "dir": viewer.direction,
            "viewer": viewer,
            **values,
        },
    )


def same_origin_only(request: Request) -> None:
    """Refuse a form submitted from another website.

    Without this, a page somewhere else can contain a hidden form aimed at this
    app. A resident who is signed in and happens to visit that page would submit
    it without knowing: their browser attaches their cookie as usual. The attack
    is called cross-site request forgery, and it needs no password, because it
    borrows a session that is already open.

    Browsers label a request with its origin. The rule here:

    * an `Origin` header that isn't ours: refuse;
    * otherwise `Sec-Fetch-Site`, which modern browsers always send: it must say
      the request came from this same site;
    * if neither header exists (an old browser, or a tool like curl): allow, and
      rely on the cookie's `SameSite=Lax` setting, which stops other sites
      sending it at all.

    Applied to every change in this app, never to reading a page.
    """
    origin = request.headers.get("origin")
    if origin:
        here = urlsplit(str(request.base_url))
        theirs = urlsplit(origin)
        if (theirs.scheme, theirs.netloc) != (here.scheme, here.netloc):
            raise HTTPException(status_code=403, detail="cross-site form submission")
        return

    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site not in ("same-origin", "same-site", "none"):
        raise HTTPException(status_code=403, detail="cross-site form submission")


SameOrigin = Annotated[None, Depends(same_origin_only)]


def permission_denied_handler(request: Request, exc: PermissionDenied):
    """Turn a refused action into a plain 403 page rather than a crash."""
    view = viewer(request)
    response = render(request, view, "denied.html", action=exc.action)
    response.status_code = 403
    return response
