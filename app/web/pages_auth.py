"""Joining the building, and signing in.

Four ways in, and no passwords anywhere:

* `/join/<code>`  a new resident, through the building's sign-up link;
* `/login`        a second phone, using a code shown on the first;
* `/signin/<code>` someone who lost their phone, with a coordinator's link;
* `/logout`       signing this phone out.

The cookie is set in one place, `_sign_in_response`, so its safety settings
cannot drift apart between routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.db import transaction
from app.services import auth
from app.web.deps import (
    SESSION_COOKIE,
    CurrentViewer,
    Database,
    SameOrigin,
    render,
)

router = APIRouter()


def _sign_in_response(token: str, destination: str = "/") -> Response:
    """Send the visitor on their way with a session cookie.

    Every setting here matters:

    * `httponly` keeps JavaScript from reading the cookie, so a stray script
      cannot steal a session;
    * `secure` sends it only over an encrypted connection, except on this
      machine, where there isn't one while building;
    * `samesite="lax"` stops other websites sending it along with their own
      requests, which is the main defence against forged forms;
    * `max_age` matches how long the session lasts in the database, so the
      cookie doesn't linger after it stops working.
    """
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,
        secure=not settings.base_url.startswith("http://localhost"),
        samesite="lax",
    )
    return response


# --- joining -----------------------------------------------------------------

@router.get("/join/{code}")
def join_form(request: Request, viewer: CurrentViewer, db: Database, code: str):
    """The sign-up form, if the link is the building's current one."""
    if code != auth.join_code(db):
        return render(request, viewer, "join_closed.html")
    return render(request, viewer, "join.html", code=code, values={}, error=None)


@router.post("/join/{code}")
def join(
    request: Request,
    viewer: CurrentViewer,
    db: Database,
    _: SameOrigin,
    code: str,
    name: str = Form(""),
    phone: str = Form(""),
    unit: str = Form(""),
    locale: str = Form("he"),
):
    """Create the account and sign the phone in.

    The new account waits for a coordinator before it can book anything, so
    signing in immediately is safe, and it lets the resident see what they are
    waiting for instead of a blank page.

    A rejected form is shown again with what was typed still in it. Retyping a
    phone number on a phone is exactly the annoyance that makes people give up.
    """
    if code != auth.join_code(db):
        return render(request, viewer, "join_closed.html")

    typed = {"name": name, "phone": phone, "unit": unit, "locale": locale}
    try:
        with transaction(db) as tx:
            person = auth.sign_up(tx, name=name, phone=phone, unit=unit, locale=locale)
            token = auth.start_session(
                tx, person.id, user_agent=request.headers.get("user-agent")
            )
    except ValueError as problem:
        return render(request, viewer, "join.html", code=code, values=typed,
                      error=str(problem))

    return _sign_in_response(token, "/me")


# --- signing in on another phone ---------------------------------------------

@router.get("/login")
def login_form(request: Request, viewer: CurrentViewer):
    """Where someone types a code from their other phone, or from a coordinator."""
    return render(request, viewer, "login.html", error=None)


@router.post("/login")
def login(
    request: Request,
    viewer: CurrentViewer,
    db: Database,
    _: SameOrigin,
    code: str = Form(""),
):
    """Spend the code and sign this phone in.

    A wrong code gets one plain message: it never says whether the code was
    unknown, expired or already used. Those differences only help someone
    guessing.
    """
    with transaction(db) as tx:
        result = auth.use_code(tx, code, user_agent=request.headers.get("user-agent"))

    if result is None:
        response = render(request, viewer, "login.html", error="login.bad_code")
        response.status_code = 400
        return response

    _, token = result
    return _sign_in_response(token, "/")


# --- a link from a coordinator ------------------------------------------------

@router.get("/signin/{code}")
def signin_confirm(request: Request, viewer: CurrentViewer, db: Database, code: str):
    """Show who this link signs in, and ask for a tap.

    Opening the link deliberately does nothing. Messaging apps fetch links to
    build a preview, and a preview that signed you in would burn the code before
    the person it was sent to ever saw it.
    """
    person = auth.peek_code(db, code)
    if person is None:
        return render(request, viewer, "signin_expired.html")
    return render(request, viewer, "signin.html", code=code, person=person)


@router.post("/signin/{code}")
def signin(request: Request, viewer: CurrentViewer, db: Database, _: SameOrigin,
           code: str):
    """The tap that actually spends the link."""
    with transaction(db) as tx:
        result = auth.use_code(tx, code, user_agent=request.headers.get("user-agent"))

    if result is None:
        return render(request, viewer, "signin_expired.html")

    _, token = result
    return _sign_in_response(token, "/")


# --- leaving ------------------------------------------------------------------

@router.post("/logout")
def logout(request: Request, db: Database, _: SameOrigin):
    """Sign this phone out, and clear the cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with transaction(db) as tx:
            auth.end_session(tx, token)

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
