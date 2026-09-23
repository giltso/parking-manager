"""Rules with no database and no web server attached.

Everything in this folder is pure: give it facts, get an answer. No file in
here opens a database, reads a request or asks what time it is; the caller
supplies all of that.

That is what makes the hardest part of this app testable. "Is space 12 free
between 14:00 and 17:00 on the morning the clocks change?" is a question about
values, and a test can ask it a hundred times a second.
"""
