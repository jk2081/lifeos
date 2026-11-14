"""The link graph: notes, people, goals and vault documents, joined by links, parent notes and record fields."""
import frappe

from lifeos import links as rules
from lifeos import permissions

TYPES = {"Life Note": "Note", "Life Person": "Person", "Life Goal": "Goal", "Life Vault Document": "Document",
	"Life Task": "Task", "Life Chat Log": "Chat", "Life Project": "Project"}
MAX_NODES = 600


@frappe.whitelist()
def get(space=None, center=None):
	"""Nodes and edges for the graph view. `center` is "DocType/name": the graph is then limited to two steps around that record."""
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

	notes = frappe.get_all("Life Note", filters={"space": space, "is_archived": 0}, fields=["name", "title", "parent_note"], order_by="modified desc", limit=300)
	for n in notes:
		add("Life Note", n.name, n.title)
	for p in frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name"], limit=100):
		add("Life Person", p.name, p.full_name)
	goals = frappe.get_all("Life Goal", filters={"space": space}, fields=["name", "title", "carried_from", "project"], order_by="creation desc", limit=100)
	for g in goals:
		add("Life Goal", g.name, g.title)
	docs = frappe.get_all("Life Vault Document", filters={"space": space, "is_archived": 0}, fields=["name", "title", "holder"], limit=100)
	for d in docs:
		add("Life Vault Document", d.name, d.title)

	link_rows = frappe.db.sql(
		"select from_doctype, from_name, to_doctype, to_name from `tabLife Link` where space=%s limit 2000", space, as_dict=True)
	for r in link_rows:  # a task, chat or project joins the graph when a link touches it
		for dt, name in ((r.from_doctype, r.from_name), (r.to_doctype, r.to_name)):
			if key(dt, name) not in nodes and dt in TYPES and frappe.db.exists(dt, name):
				add(dt, name, rules.title_of(dt, name))
		edge(key(r.from_doctype, r.from_name), key(r.to_doctype, r.to_name), "link")
	for n in notes:
		if n.parent_note:
			edge(key("Life Note", n.name), key("Life Note", n.parent_note), "parent")
	for d in docs:
		if d.holder:
			edge(key("Life Vault Document", d.name), key("Life Person", d.holder), "holder")
	for g in goals:
		if g.carried_from:
			edge(key("Life Goal", g.name), key("Life Goal", g.carried_from), "carried")
		if g.project and frappe.db.exists("Life Project", g.project):
			add("Life Project", g.project, frappe.db.get_value("Life Project", g.project, "title"))
			edge(key("Life Goal", g.name), key("Life Project", g.project), "project")

	if center:
		if center not in nodes:
			dt, _, name = center.partition("/")
			if dt in TYPES and frappe.db.get_value(dt, {"name": name, "space": space}):
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
