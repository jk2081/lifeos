"""Insights for the screens (UX fixes, set 5): the Ask page's Insights tab, Today's Next list and rail. People only."""
import frappe
from frappe import _
from frappe.query_builder import Order

from lifeos.review import insights as rules
from lifeos import permissions
from lifeos.api.utils import count_by, count_where, list_query, names_map, page, parse

STATUSES = ("New", "Snoozed", "Acted", "Dismissed")


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Insights are for people."), frappe.PermissionError, title=_("Insights are for people"))


def _out(rows):
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	ev = {}
	if rows:
		for p, dt, n, label in frappe.get_list("Life Insight Evidence", filters={"parent": ("in", [r.name for r in rows])}, fields=["parent", "ref_doctype", "ref_name", "label"],
				order_by="idx", parent_doctype="Life Insight", limit=0, as_list=True):
			ev.setdefault(p, []).append({"doctype": dt, "name": n, "label": label})
	from lifeos.web.pane_refs import ref_of

	for r in rows:
		r["area_name"] = areas.get(r.area)
		r["evidence"] = [{**e, "ref": ref_of(e["doctype"], e["name"])} for e in ev.get(r.name, [])]
		r["based_on"] = based_on(r["evidence"])
		r["actions"] = parse(r.get("actions"), []) or []
		r["actionable"] = r.kind in rules.ACTIONABLE
		for k in ("found_on", "snooze_until", "creation"):
			if r.get(k):
				r[k] = str(r[k])[:10]
	return rows


LABEL = {"Life Task": ("task", "tasks"), "Life Goal": ("goal", "goals"), "Life Chat Log": ("chat", "chats"),
	"Life Inbox Item": ("source", "sources"), "Life Note": ("note", "notes"),
	"Life Habit": ("habit log", "habit logs"), "Life Cycle": ("12 Week Year", "12 Week Years")}


def based_on(evidence):
	"""'Based on 4 chats, 1 note' from the evidence."""
	by = {}
	for e in evidence:
		by[e["doctype"]] = by.get(e["doctype"], 0) + 1
	if len(evidence) == 1:
		e = evidence[0]
		return f"Based on {e['label'] or LABEL.get(e['doctype'], (e['doctype'],))[0]}"
	return "Based on " + ", ".join(f"{n} {LABEL.get(dt, (dt, dt + 's'))[0 if n == 1 else 1]}" for dt, n in by.items())


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, status: str | None = "New", kind: str | None = None, area: str | None = None,
		start: int | str | None = 0, page_length: int | str | None = 50, actionable: int | str | None = None):
	"""Insights of a space: status New (default), Snoozed, Acted, Dismissed or all; kind; area; actionable=1 or 0.
	`tabs` counts each status under the other filters."""
	_person()
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	i = frappe.qb.DocType("Life Insight")
	where = [i.space == space]
	if kind:
		where.append(i.kind == kind)
	if area:
		where.append(i.area == area)
	if actionable not in (None, ""):
		where.append(i.kind.isin(rules.ACTIONABLE) if int(actionable) else i.kind.notin(rules.ACTIONABLE))
	tabs = {s: 0 for s in STATUSES}
	tabs.update(count_by("Life Insight", "status", where))
	tabs["all"] = sum(tabs.values())
	kinds = list_query("Life Insight", ["kind"], where).distinct().run(pluck=True)
	if status and status != "all":
		where.append(i.status == status)
	fields = ["name", "kind", "title", "body", "status", "snooze_until", "source", "area", "found_on", "actions", "dismiss_reason", "acted_note", "creation"]
	rows = list_query("Life Insight", fields, where, [(i.rank, Order.asc), (i.creation, Order.desc)]).limit(page_length).offset(start).run(as_dict=True)
	total = count_where("Life Insight", where)
	return {"rows": _out(rows), "total": total, "tabs": tabs, "kinds": kinds,
		"run_on": _run_on()}


def _run_on():
	v = frappe.db.get_single_value("Life Settings", "insights_run_on")
	return str(v)[:16] if v and getattr(v, "year", 0) > 1900 else None


@frappe.whitelist(methods=["POST"])
def refresh(space: str | None = None):
	"""Find insights now (Refresh insights)."""
	_person()
	space = permissions.resolve_space(space)
	ai = bool(frappe.db.get_value("Life Space", space, "ask_enabled"))
	return rules.run(space, ai=ai)


def _doc(name):
	_person()
	return permissions.get_doc_checked("Life Insight", name, "write")


@frappe.whitelist(methods=["POST"])
def act(insight: str, index: int | str = 0):
	"""Run one of an insight's suggested actions, with the person's own permissions. Navigation actions are done by the
	screen; this records them. Returns what the screen needs (a route, a created record, Undo)."""
	doc = _doc(insight)
	actions = parse(doc.actions, []) or []
	try:
		a = actions[int(index)]
	except (IndexError, ValueError, TypeError):
		frappe.throw(_("No such action."), title=_("Unknown insight action"))
	out = {"kind": a.get("kind")}
	if a.get("kind") == "make_task":
		from lifeos.api import chats, tasks

		if a.get("chat") and a.get("row"):
			res = chats.make_task(a["chat"], a["row"])
			out["task"] = res.get("task") if isinstance(res, dict) else res
		else:
			t = tasks.quick_add(a.get("title") or doc.title, space=doc.space, area=a.get("area"))
			out["task"] = t["name"]
		doc.acted_note = "task made"
	elif a.get("kind") == "move_someday":
		from lifeos.api import reset

		res = reset.apply_batch("someday", a.get("items") or [], space=doc.space)
		out["undo"] = res["undo"]
		out["done"] = res["done"]
		doc.acted_note = f"{res['done']} moved to Someday"
	elif a.get("kind") in ("open_reset", "open_list", "open_record"):
		out.update({k: a.get(k) for k in ("names", "to", "ref")})
		doc.acted_note = "opened"
		if a.get("kind") != "open_reset":
			return out  # looking is not acting: the insight stays New
	else:
		frappe.throw(_("Unknown action."), title=_("Unknown insight action"))
	doc.status = "Acted"
	doc.save()
	return out
