"""The weekly review (set 8): a guided review in four tabs (Library, Tasks, Goals, Reflect) kept in one `Life Review`.

- record.py: the review itself, its period, where it was left, and which tabs are done.
- stale.py: the stale tasks of the Tasks tab, each with Keep, Someday and Drop.
- findings.py: the revelations (one Life Insight per finding, cleared everywhere at once).
- meetings.py and gcal.py: meetings read from Google Calendar, which ones matter, and what was captured around them.
- library.py, goals.py, lock.py: the data of tabs 1, 3 and 4, and Lock the week.

The shell (period, tabs, drawers) is built so a Monthly or a 12 Weeks review can reuse it with tabs of its own.
"""
