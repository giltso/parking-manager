"""The app itself: what starts, what it serves.

This file is deliberately thin. It wires pieces together and owns no rules of
its own: those live in the modules it imports. Right now it serves two things,
a health check and a home page, which is enough to prove the skeleton works
end to end.

To run it while building:

    .venv/Scripts/python -m uvicorn app.main:app --reload

`--reload` restarts the app whenever a file is saved.
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import i18n
from app.clock import now_utc, to_building_time
from app.config import settings
from app.db import connect, migrate

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the app starts, and once when it stops.

    Bringing the database up to date here means there is no separate "set up
    the database" step to forget, on this machine or in the container. Running
    migrations is safe to repeat: already-applied ones are skipped.

    Everything before `yield` happens at startup, everything after at shutdown.
    """
    connection = connect()
    applied = migrate(connection)
    app.state.db = connection
    app.state.migrations_applied = applied

    yield

    connection.close()


app = FastAPI(
    title="Parking Manager",
    lifespan=lifespan,
    # The automatic API documentation pages are for developers, and this app's
    # audience is residents, so they stay off.
    docs_url=None,
    redoc_url=None,
)

# Files served exactly as they are: stylesheet, icons, and later the small
# JavaScript library the pages use. Kept in the project rather than loaded from
# someone else's server, so the app has no outside dependency at runtime.
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/healthz")
def healthz(request: Request) -> JSONResponse:
    """A one-line answer to "is this app alive and able to reach its database?".

    Deployment tools and monitors call this. It deliberately touches the
    database, because an app that answers while its database is unreachable is
    worse than one that admits the problem.

    The name is a convention (the "z" avoids clashing with a real page).
    """
    try:
        connection: sqlite3.Connection = request.app.state.db
        connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        return JSONResponse(
            {"status": "unhealthy", "error": str(exc)},
            status_code=503,  # "service unavailable"
        )

    return JSONResponse({
        "status": "ok",
        "time_utc": now_utc().isoformat(),
        "time_building": to_building_time(now_utc()).isoformat(),
        "schema": request.app.state.migrations_applied,
    })


def _safe_next(referer: str | None, base_url: str) -> str:
    """Turn a browser-supplied `Referer` into a page of this app, or "/".

    The rule is "same site or home". A plain path ("/spaces") is fine. A full
    address is fine only if it is this app's own. Anything else, including
    "https://elsewhere.example/spaces", becomes "/".

    Keeping only the path of a foreign address would be the subtle mistake: it
    stays on this site, but it sends the visitor to whatever page the attacker
    chose, which is not where they were.
    """
    if not referer:
        return "/"

    where = urlsplit(referer)
    here = urlsplit(base_url)

    if where.scheme or where.netloc:
        # A full address: only our own counts.
        if (where.scheme, where.netloc) != (here.scheme, here.netloc):
            return "/"
    elif not referer.startswith("/") or referer.startswith("//"):
        # A bare path must really be a path. "//elsewhere.example" looks like
        # one but browsers read it as another site.
        return "/"

    path = where.path or "/"
    return f"{path}?{where.query}" if where.query else path


@app.post("/lang")
def set_language(request: Request, to: str = Form(...)):
    """Remember the visitor's language choice and send them back where they were.

    The choice is kept in a cookie, which is a small note the browser hands back
    on every later request. A guest has no account to store it on, so a cookie
    is the only place it can live.

    `max_age` is a year in seconds. `samesite="lax"` means the cookie is not
    sent when another website makes a request to us, which is the standard
    defence against other sites acting in a visitor's name.

    The page to return to comes from the `Referer` header, which the browser
    fills in and therefore cannot be trusted. `_safe_next` reduces it to a page
    of this app, or the home page. Without that, a crafted link could bounce a
    resident to another site dressed up as this one, a trick called an open
    redirect.
    """
    language = to if to in i18n.LANGUAGES else settings.default_locale
    back_to = _safe_next(request.headers.get("referer"), str(request.base_url))
    response = RedirectResponse(back_to, status_code=303)
    response.set_cookie(
        "lang",
        language,
        max_age=365 * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/")
def home(request: Request):
    """The home page. For now it only proves the shell works in both languages.

    The language comes from the visitor's own choice or their browser (see
    app/i18n.py), and the whole page flips direction with it.
    """
    language = i18n.choose_language(
        cookie_value=request.cookies.get("lang"),
        accept_language=request.headers.get("accept-language"),
    )
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "t": i18n.translator(language),
            "lang": language,
            "dir": i18n.direction(language),
        },
    )
