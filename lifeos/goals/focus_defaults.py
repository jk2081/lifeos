"""The focuses Life OS offers for each kind of part, with a suggested standard (issue 57). One file, so it is easy to change.
A part's kind is picked when it is created or edited; each focus is offered as a switch, all on."""

KINDS = ("Company", "Estate", "Household", "Other")

FOCUSES = {
	"Company": [
		("Review cadence", "Every number that matters is looked at on a fixed day, by the same people."),
		("Systems", "Work runs from written processes and one system of record, not from memory."),
		("Marketing", "A steady, known flow of the right enquiries."),
		("People", "The right people are in the right seats and know what is expected of them."),
		("Finance", "Cash, margins and dues are known weekly, and no payment is a surprise."),
	],
	"Estate": [
		("Yield", "Yield is measured every cycle and rises year on year."),
		("Quality", "Produce meets its grade every time, and the grade is tracked."),
		("People", "The estate has a trained team that stays, and it is paid on time."),
		("Systems", "The manager sees yesterday's numbers by 9 am, from one system."),
	],
	"Household": [
		("Home", "The home is safe, repaired in time and in order."),
		("Money admin", "Bills, taxes and renewals are paid before they are due."),
		("Health admin", "Check-ups, insurance and medicines are kept up to date."),
	],
	"Other": [],
}


def offered(kind):
	"""[(name, standard)] offered for a kind of part: none for Other or an unknown kind."""
	return list(FOCUSES.get(kind or "", []))
