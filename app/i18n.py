"""Hebrew and English text, and the page direction that goes with each.

Every visible string lives here rather than in the templates, so adding or
fixing a translation never means hunting through HTML.

Two things travel together:

* the **words**, looked up by a short key such as "app.name";
* the **direction**, because Hebrew reads right to left. That is not just text
  alignment: the whole page mirrors, so a back arrow points the other way.

Numbers, phone numbers and licence plates always read left to right, even
inside a Hebrew sentence, or "050-1234567" comes out backwards. Templates wrap
those in <bdi dir="ltr">, which is HTML's way of saying "this fragment keeps its
own direction".
"""

from __future__ import annotations

from app.config import settings

# The languages the app speaks, and which way each is written.
LANGUAGES: dict[str, dict[str, str]] = {
    "he": {"name": "עברית", "dir": "rtl"},
    "en": {"name": "English", "dir": "ltr"},
}

# The text itself: one entry per key, one line per language.
# Keys are grouped by area, so related text sits together.
TEXT: dict[str, dict[str, str]] = {
    "app.name": {
        "he": "חניה בבניין",
        "en": "Building Parking",
    },
    "app.tagline": {
        "he": "שיתוף חניות בין שכנים",
        "en": "Sharing parking between neighbours",
    },
    "home.building": {
        "he": "השלד עובד. המסכים עוד לא נבנו.",
        "en": "The skeleton is running. The screens aren't built yet.",
    },
    "home.next": {
        "he": "השלב הבא: זמני פנייה ושעות פתיחה.",
        "en": "Next step: opening hours and availability.",
    },
    "lang.switch": {
        "he": "English",
        "en": "עברית",
    },
}


def choose_language(
    cookie_value: str | None = None,
    accept_language: str | None = None,
) -> str:
    """Decide which language to use for this visitor.

    In order of preference:

    1. the language they chose before, remembered in a cookie;
    2. the language their phone asks for, in the `Accept-Language` header the
       browser sends with every request;
    3. the building's default, which is Hebrew.

    Anything unrecognised falls through to the next choice, so a browser asking
    for Japanese gets Hebrew rather than an error.
    """
    if cookie_value in LANGUAGES:
        return cookie_value

    if accept_language:
        # The header looks like "he-IL,he;q=0.9,en-US;q=0.8". We only need the
        # first two letters of each entry, in the order given.
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower()[:2]
            if code in LANGUAGES:
                return code

    return settings.default_locale if settings.default_locale in LANGUAGES else "he"


def translator(language: str):
    """Return a function that turns a key into text in `language`.

    Templates call it `t`, so the HTML reads `{{ t("app.name") }}`.

    A missing key returns the key itself rather than raising. A half-translated
    page is a nuisance; a page that won't load is a fault.
    """
    def t(key: str) -> str:
        entry = TEXT.get(key)
        if entry is None:
            return key
        return entry.get(language) or entry.get("en") or key

    return t


def direction(language: str) -> str:
    """'rtl' for Hebrew, 'ltr' for English."""
    return LANGUAGES.get(language, LANGUAGES["he"])["dir"]


def missing_keys() -> dict[str, list[str]]:
    """Which keys lack a translation, per language. Used by the tests.

    Catching this in a test is the difference between noticing on your machine
    and a neighbour noticing an English sentence in a Hebrew screen.
    """
    gaps: dict[str, list[str]] = {}
    for language in LANGUAGES:
        absent = [key for key, entry in TEXT.items() if not entry.get(language)]
        if absent:
            gaps[language] = absent
    return gaps
