"""Issue 98: search reads Frappe's Global Search. Mark the searched fields and index the records that already exist."""
from lifeos.library import globalsearch


def execute():
	globalsearch.install()
	globalsearch.rebuild()
