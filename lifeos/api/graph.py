"""The link graph: notes, people, goals and vault documents, joined by links, parent notes and record fields."""
import frappe

from lifeos.library import links as rules
from lifeos import permissions
from lifeos.api.utils import in_area, lens_area

TYPES = {"Life Note": "Note", "Life Person": "Person", "Life Goal": "Goal", "Life Vault Document": "Document",
	"Life Task": "Task", "Life Chat Log": "Chat"}
MAX_NODES = 600
VAULT = "Life Vault Document"


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, center: str | None = None, collection: str | None = None, area: str | None = None):
	"""Nodes and edges for the graph view. `center` is "DocType/name": the graph is then limited to two steps around that record.
	collection (Wiki or My notes) starts the graph from the notes of that collection only; linked records still join it."""
	space = permissions.resolve_space(space)
	nodes, edges = {}, []

	def key(dt, name):
		return f"{dt}/{name}"

	def add(dt, name, label):
		k = key(dt, name)
		if k not in nodes and len(nodes) < MAX_NODES:
			nodes[k] = {"id": k, "label": label or name, "type": TYPES.get(dt, dt.replace("Life ", "")), "route": rules.route_of(dt, name)}
		return k in nodes

	def edge(a, b, kind):
		if a in nodes and b in nodes and a != b:
			edges.append({"source": a, "target": b, "kind": kind})

	note_filters = {"space": space, "is_archived": 0, **({"is_sensitive": 0} if permissions.vault_hidden(space) else {})}
	if collection in ("Wiki", "My notes"):
		note_filters["collection"] = collection
	notes = frappe.get_list("Life Note", filters=note_filters, fields=["name", "title", "parent_note"], order_by="modified desc", limit=300)
	area = lens_area(area)
	if area:  # the lens: the graph starts from the area's notes and goals; linked records still join it
		keep = in_area(space, area, "Life Note", [n.name for n in notes])
		notes = [n for n in notes if n.name in keep]
	for n in notes:
		add("Life Note", n.name, n.title)
	for p in ([] if collection or area else frappe.get_list("Life Person", filters={"space": space}, fields=["name", "full_name"], limit=100)):
		add("Life Person", p.name, p.full_name)
	goals = [] if collection else frappe.get_list("Life Goal", filters={"space": space}, fields=["name", "title", "carried_from", "serves"], order_by="creation desc", limit=100)
	if area:
		keep = in_area(space, area, "Life Goal", [g.name for g in goals])
		goals = [g for g in goals if g.name in keep]
	for g in goals:
		add("Life Goal", g.name, g.title)
	docs = [] if permissions.vault_hidden(space) or collection or area else frappe.get_list("Life Vault Document", filters={"space": space, "is_archived": 0}, fields=["name", "title", "holder"], limit=100)
	for d in docs:
		add("Life Vault Document", d.name, d.title)

	link_rows = frappe.db.sql(
		"select from_doctype, from_name, to_doctype, to_name from `tabLife Link` where space=%s limit 2000", space, as_dict=True)
	hidden = {VAULT} if permissions.vault_hidden(space) else set()
	ends = [(dt, name) for r in link_rows for dt, name in ((r.from_doctype, r.from_name), (r.to_doctype, r.to_name))
		if dt in TYPES and dt not in hidden and key(dt, name) not in nodes]
	found = titles(ends)
	if hidden:  # sensitive items join an agent's graph only when the space's switch allows it (set 6)
		for dt in permissions.SENSITIVE_DOCTYPES:
			names = [n for d, n in found if d == dt]
			for n in frappe.get_list(dt, filters={"name": ("in", names or ["-"]), "is_sensitive": 1}, pluck="name"):
				found.pop((dt, n), None)
	for r in link_rows:  # a task or chat joins the graph when a link touches it
		for dt, name in ((r.from_doctype, r.from_name), (r.to_doctype, r.to_name)):
			if key(dt, name) not in nodes and (dt, name) in found:
				add(dt, name, found[(dt, name)])
		edge(key(r.from_doctype, r.from_name), key(r.to_doctype, r.to_name), "link")
	for n in notes:
		if n.parent_note:
			edge(key("Life Note", n.name), key("Life Note", n.parent_note), "parent")
	for d in docs:
		if d.holder:
			edge(key("Life Vault Document", d.name), key("Life Person", d.holder), "holder")
	served = titles([("Life Goal", g.serves) for g in goals if g.serves])
	for g in goals:
		if g.carried_from:
			edge(key("Life Goal", g.name), key("Life Goal", g.carried_from), "carried")
		if g.serves and ("Life Goal", g.serves) in served:
			add("Life Goal", g.serves, served[("Life Goal", g.serves)])
			edge(key("Life Goal", g.name), key("Life Goal", g.serves), "serves")

	if center:
		if center not in nodes:
			dt, _, name = center.partition("/")
			if dt in TYPES and dt not in hidden and frappe.db.get_value(dt, {"name": name, "space": space}):
				add(dt, name, rules.title_of(dt, name))
		keep, frontier = {center}, {center}
		for _step in range(2):
			nxt = set()
			for e in edges:
				if e["source"] in frontier and e["target"] not in keep:
					nxt.add(e["target"])
				if e["target"] in frontier and e["source"] not in keep:
					nxt.add(e["source"])
			keep |= nxt
			frontier = nxt
		nodes = {k: v for k, v in nodes.items() if k in keep}
		edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]

	seen, unique = set(), []
	for e in edges:
		k = (e["source"], e["target"], e["kind"])
		if k not in seen:
			seen.add(k)
			unique.append(e)
	return {"space": space, "center": center, "nodes": list(nodes.values()), "edges": unique, "capped": len(nodes) >= MAX_NODES}


def titles(refs):
	"""{(doctype, name): title} for the records that exist, one query per DocType."""
	by_type = {}
	for dt, name in refs:
		by_type.setdefault(dt, set()).add(name)
	out = {}
	for dt, names in by_type.items():
		field = rules.LINKABLE.get(dt) or "title"
		field = field if frappe.get_meta(dt).has_field(field) else "name"
		for name, title in frappe.get_list(dt, filters={"name": ("in", sorted(names))}, fields=["name", field], as_list=True):
			out[(dt, name)] = title
	return out
