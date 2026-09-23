"""The screens: read a request, call a service, render a template.

Nothing in here decides a rule or writes SQL. A route works out who is asking,
asks `app/permissions.py` whether they may, calls a service, and renders the
result. Keeping routes this thin is what lets the rules be tested without a
browser, and what will let a later version add credits without touching screens.
"""
