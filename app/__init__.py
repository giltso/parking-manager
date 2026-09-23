"""The parking-sharing app.

Layout (see PLAN.md section 2.1):

    config.py       every setting, read from the environment
    clock.py        the only source of "what time is it"
    db.py           opening the database and applying migrations
    permissions.py  who may do what
    i18n.py         Hebrew and English text
    main.py         the app: what it serves

Later steps add `domain/` (rules with no database), `services/` (the only code
that changes data) and `web/` (routes).
"""
