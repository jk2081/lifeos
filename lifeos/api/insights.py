"""Insights for the screens (UX fixes, set 5): the Ask page's Insights tab, Today's Next list and rail. People only."""
import json
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import insights as rules
from lifeos import permissions
from lifeos.api.utils import names_map, page, parse

STATUSES = ("New", "Snoozed", "Acted", "Dismissed")


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Insights are for people."), frappe.PermissionError)


def _out(rows):
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	ev = {}
	if rows:
		for p, dt, n, label in frappe.db.sql("""select parent, ref_doctype, ref_name, label from `tabLife Insight Evidence`
			where parent in %s order by idx""", ([r.name for r in rows],)):
			ev.setdefault(p, []).append({"doctype": dt, "name": n, "label": label})
	from lifeos.pane_refs import ref_of

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
	"Life Inbox Item": ("source", "sources"), "Life Note": ("note", "notes"), "Life Check-in": ("check-in", "check-ins"),
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
	where, values = ["space=%(space)s"], {"space": space}
	if kind:
		where.append("kind=%(kind)s")
		values["kind"] = kind
	if area:
		where.append("area=%(area)s")
		values["area"] = area
	if actionable not in (None, ""):
		where.append(("" if int(actionable) else "not ") + "kind in %(act)s")
		values["act"] = rules.ACTIONABLE
	base = " and ".join(where)
	tabs = {s: 0 for s in STATUSES}
	# nosemgrep: frappe-sql-format-injection -- WHERE is joined from fixed fragments; every value is a parameter
	for s, n in frappe.db.sql(f"select status, count(*) from `tabLife Insight` where {base} group by status", values):
		tabs[s] = n
	tabs["all"] = sum(tabs.values())
	if status and status != "all":
		where.append("status=%(status)s")
		values["status"] = status
	clause = " and ".join(where)
	# nosemgrep: frappe-sql-format-injection -- WHERE is joined from fixed fragments; every value is a parameter
	rows = frappe.db.sql(f"""select name, kind, title, body, status, snooze_until, source, area, found_on, actions, dismiss_reason, acted_note, creation
		from `tabLife Insight` where {clause} order by rank asc, creation desc limit %(start)s, %(len)s""", {**values, "start": start, "len": page_length}, as_dict=True)
	# nosemgrep: frappe-sql-format-injection -- WHERE is joined from fixed fragments; every value is a parameter
	total = frappe.db.sql(f"select count(*) from `tabLife Insight` where {clause}", values)[0][0]
	kinds = frappe.db.sql_list(f"select distinct kind from `tabLife Insight` where {base}", values)
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
def dismiss(insight: str, reason: str | None = None):
	"""Dismiss, with an optional reason (not relevant, already done, wrong). The AI reads the last 30 with their reasons."""
	doc = _doc(insight)
	if reason and reason not in ("Not relevant", "Already done", "Wrong"):
		frappe.throw(_("reason must be Not relevant, Already done or Wrong."))
	doc.status, doc.dismiss_reason = "Dismissed", reason or ""
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def snooze(insight: str, until: str | date | None = None):
	doc = _doc(insight)
	doc.status, doc.snooze_until = "Snoozed", until or add_days(today(), 7)
	doc.save()
	return {"status": doc.status, "snooze_until": str(doc.snooze_until)}


@frappe.whitelist(methods=["POST"])
def restore(insight: str):
	"""Undo a dismiss, a snooze or an act: back to New."""
	doc = _doc(insight)
	doc.status, doc.snooze_until, doc.dismiss_reason = "New", None, ""
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def act(insight: str, index: int | str = 0):
	"""Run one of an insight's suggested actions, with the person's own permissions. Navigation actions are done by the
	screen; this records them. Returns what the screen needs (a route, a created record, Undo)."""
	doc = _doc(insight)
	actions = parse(doc.actions, []) or []
	try:
		a = actions[int(index)]
	except (IndexError, ValueError, TypeError):
		frappe.throw(_("No such action."))
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
		frappe.throw(_("Unknown action."))
	doc.status = "Acted"
	doc.save()
	return out


@frappe.whitelist(methods=["GET"])
def summary(space: str | None = None):
	"""Today's use: actionable New insights for Next, and the rest in one line for the rail."""
	_person()
	space = permissions.resolve_space(space)
	act_rows = list(space=space, status="New", actionable=1, page_length=20)
	rest = list(space=space, status="New", actionable=0, page_length=5)
	return {"actionable": act_rows["rows"], "actionable_total": act_rows["total"], "other": rest["rows"], "other_total": rest["total"]}
