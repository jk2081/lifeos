"""Issue 25: link the existing Wiki pages to the people and organisations they describe. A page whose title matches a Life
Person (or one of their other names) is linked; a page that reads like a company gets an Organisation; a page about a
person with no matching Life Person is listed, not guessed. Running it again changes nothing."""
from lifeos import people


def execute():
	out = people.link_existing()
	print(f"People: linked {len(out['linked'])} wiki page(s) to a Life Person, made {len(out['created'])} organisation(s).")
	if out["undecided"]:
		print("People: could not decide (create the Life Person, or give the page's person another name):")
		for name, title, why in out["undecided"]:
			print(f"  - {title} ({name}): {why}")
