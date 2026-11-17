"""Pre-step 6: the composite indexes added for Today's counts (the Notes list and its "not opened" count, the Inbox's
state tabs, goals with no tasks, an agent's last filing). ensure_indexes adds only what is missing, so this can run again."""
from lifeos import index


def execute():
	index.ensure_indexes()
