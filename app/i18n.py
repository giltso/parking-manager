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

    # --- shared words ------------------------------------------------------
    "field.name": {"he": "שם", "en": "Name"},
    "field.phone": {"he": "טלפון", "en": "Phone"},
    "field.unit": {"he": "דירה", "en": "Apartment"},
    "field.language": {"he": "שפה", "en": "Language"},
    "action.save": {"he": "שמירה", "en": "Save"},
    "action.remove": {"he": "הסרה", "en": "Remove"},
    "action.sign_out": {"he": "התנתקות", "en": "Sign out"},
    "action.approve": {"he": "אישור", "en": "Approve"},
    "action.reject": {"he": "דחייה", "en": "Reject"},
    "action.deactivate": {"he": "השבתה", "en": "Deactivate"},
    "nav.me": {"he": "הפרופיל שלי", "en": "My profile"},
    "nav.coordinator": {"he": "ניהול", "en": "Coordinator"},
    "nav.sign_in": {"he": "כניסה", "en": "Sign in"},

    "status.pending": {"he": "ממתין לאישור", "en": "waiting for approval"},
    "status.approved": {"he": "מאושר", "en": "approved"},
    "status.rejected": {"he": "נדחה", "en": "rejected"},
    "status.deactivated": {"he": "מושבת", "en": "deactivated"},
    "role.coordinator": {"he": "רכז", "en": "coordinator"},

    # --- joining -----------------------------------------------------------
    "join.title": {"he": "הצטרפות", "en": "Join"},
    "join.intro": {
        "he": "אחרי ההרשמה רכז הבניין יאשר את החשבון, ואז אפשר להזמין חניה.",
        "en": "After signing up, a coordinator approves the account and then you can book.",
    },
    "join.submit": {"he": "הרשמה", "en": "Sign up"},
    "join.error": {
        "he": "משהו בפרטים לא תקין. בדקו את מספר הטלפון ונסו שוב.",
        "en": "Something in the details isn't right. Check the phone number and try again.",
    },
    "join.closed_title": {"he": "הקישור כבר לא פעיל", "en": "This link is no longer active"},
    "join.closed_body": {
        "he": "בקשו מרכז הבניין את הקישור העדכני.",
        "en": "Ask a building coordinator for the current link.",
    },

    # --- signing in --------------------------------------------------------
    "login.title": {"he": "כניסה עם קוד", "en": "Sign in with a code"},
    "login.intro": {
        "he": "הקוד מופיע בטלפון שכבר מחובר, תחת הפרופיל.",
        "en": "The code is shown on a phone that is already signed in, under the profile.",
    },
    "login.code": {"he": "קוד", "en": "Code"},
    "login.submit": {"he": "כניסה", "en": "Sign in"},
    "login.bad_code": {
        "he": "הקוד לא מתאים או שפג תוקפו. אפשר להנפיק קוד חדש.",
        "en": "That code doesn't work or has expired. A new one can be issued.",
    },
    "signin.title": {"he": "להיכנס בתור", "en": "Sign in as"},
    "signin.submit": {"he": "כניסה", "en": "Sign in"},
    "signin.expired_title": {"he": "הקישור פג", "en": "This link has expired"},
    "signin.expired_body": {
        "he": "קישורי כניסה תקפים לשבוע ולשימוש אחד. בקשו קישור חדש מרכז הבניין.",
        "en": "Sign-in links last a week and work once. Ask a coordinator for a new one.",
    },

    # --- profile -----------------------------------------------------------
    "me.title": {"he": "הפרופיל שלי", "en": "My profile"},
    "me.waiting": {
        "he": "החשבון ממתין לאישור רכז. עד אז אפשר להסתכל, אך לא להזמין חניה.",
        "en": "This account is waiting for a coordinator. Until then you can look, but not book.",
    },
    "me.details": {"he": "פרטים", "en": "Details"},
    "me.error": {
        "he": "משהו בפרטים לא תקין. בדקו את מספר הטלפון ונסו שוב.",
        "en": "Something in the details isn't right. Check the phone number and try again.",
    },
    "me.cars": {"he": "רכבים", "en": "Cars"},
    "me.cars_hint": {
        "he": "אפשר להוסיף מספר רכבים, או לא להוסיף בכלל. בעל החניה רואה איזה רכב אמור לעמוד אצלו.",
        "en": "Add as many as you like, or none. A space's owner sees which car should be there.",
    },
    "me.add_car": {"he": "הוספת רכב", "en": "Add car"},
    "me.devices": {"he": "מכשירים מחוברים", "en": "Signed-in devices"},
    "me.devices_hint": {
        "he": "טלפון שאבד? נתקו אותו כאן.",
        "en": "Lost a phone? Sign it out here.",
    },
    "me.unknown_device": {"he": "מכשיר לא מזוהה", "en": "Unrecognised device"},
    "me.sign_out_device": {"he": "ניתוק", "en": "Sign out"},
    "me.add_device": {"he": "חיבור טלפון נוסף", "en": "Add another phone"},
    "me.device_code_title": {"he": "קוד לטלפון הנוסף", "en": "Code for the other phone"},
    "me.device_code_hint": {
        "he": "הקלידו את הקוד בטלפון השני תוך עשר דקות. הקוד מוצג פעם אחת בלבד.",
        "en": "Type this on the other phone within ten minutes. It is shown once only.",
    },

    # --- coordinator -------------------------------------------------------
    "coordinator.title": {"he": "ניהול הבניין", "en": "Building coordination"},
    "coordinator.people": {"he": "דיירים", "en": "Residents"},
    "coordinator.join_link": {"he": "קישור ההרשמה", "en": "Sign-up link"},
    "coordinator.join_hint": {
        "he": "שתפו בקבוצת הבניין. כל הרשמה ממתינה לאישור שלכם.",
        "en": "Share it in the building's group. Every sign-up waits for your approval.",
    },
    "coordinator.rotate": {"he": "החלפת הקישור", "en": "Replace the link"},
    "coordinator.signin_link": {"he": "קישור כניסה חד-פעמי", "en": "One-time sign-in link"},
    "coordinator.signin_hint": {
        "he": "שלחו לדייר. תקף לשבוע ולשימוש אחד, ולא ניתן להציג שוב.",
        "en": "Send it to the resident. It lasts a week, works once, and cannot be shown again.",
    },
    "coordinator.new_link": {"he": "קישור כניסה", "en": "Sign-in link"},

    # --- refusals ----------------------------------------------------------
    "denied.title": {"he": "אין הרשאה", "en": "Not allowed"},
    "denied.body": {
        "he": "הפעולה הזו לא זמינה לחשבון הזה.",
        "en": "This account cannot do that.",
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
