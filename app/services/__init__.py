"""The only code allowed to read and change stored data.

Screens never write SQL. They call a service, which loads what it needs, asks
the pure rules in `app/domain/` for a decision, writes the result and records
what happened. Keeping that in one layer is what will let a later version add
credits or payments without touching a single screen.
"""
