"""Set 6, the lens: every area gets a colour for its dot, and the top-level areas of each space are pinned to the sidebar
(the default the owner can change in Settings > Areas). Only areas without a colour, and spaces with no pinned area, are
touched, so this can run again."""
import frappe

COLOURS = ["blue", "green", "amber", "violet", "red", "teal", "orange", "pink", "cyan", "gray"]


def execute():
	for space in frappe.get_all("Life Space", pluck="name"):
		areas = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "parent_area", "colour", "is_pinned"],
			order_by="sort_order asc, area_name asc", limit=2000)
		top = [a for a in areas if not a.parent_area]
		for i, a in enumerate(top):
			if not a.colour:
				frappe.db.set_value("Life Area", a.name, "colour", COLOURS[i % len(COLOURS)], update_modified=False)
		colour_of = {a.name: a.colour or COLOURS[top.index(a) % len(COLOURS)] for a in top}
		for a in areas:
			if a.parent_area and not a.colour:
				frappe.db.set_value("Life Area", a.name, "colour", colour_of.get(a.parent_area, "gray"), update_modified=False)
		if not any(a.is_pinned for a in areas):
			for a in top:
				frappe.db.set_value("Life Area", a.name, "is_pinned", 1, update_modified=False)
