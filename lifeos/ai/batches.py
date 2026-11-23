"""Reset's suggested batches: open tasks that no rule batch has taken are given to the tidy-backlog skill, and the ones it parks or
drops that it grouped together become batches (at most three), each with its reason. Tasks it names that were not given are ignored."""
import frappe
from frappe.query_builder import functions as fn
from frappe.utils import date_diff, today

MAX_CANDIDATES = 150
MAX_BATCHES = 3
ACTIONS = {"park": ("someday", "Move {n} to Someday"), "drop": ("drop", "Drop {n}")}


def suggest(space, rule_batches):
	from lifeos.api.reset import _batch, _item
	from lifeos.skills import call

	taken = {i["name"] for b in rule_batches for i in b["items"]}
	t, a, p = frappe.qb.DocType("Life Task"), frappe.qb.DocType("Life Area"), frappe.qb.DocType("Life Goal")
	touched = fn.IfNull(t.last_touched_on, fn.Date(t.creation))
	rows = (frappe.qb.from_(t).left_join(a).on(a.name == t.area).left_join(p).on(p.name == t.goal).select(t.name, t.title, a.area_name, p.title.as_("goal"), touched.as_("touched"))
		.where((t.space == space) & t.status.isin(["Open", "Doing", "Waiting"]) & (t.is_archived == 0)).orderby(touched).limit(MAX_CANDIDATES + len(taken)).run(as_dict=True))  # system: Reset reads the owner's own space
	cands = [r for r in rows if r.name not in taken][:MAX_CANDIDATES]
	if len(cands) < 3:
		return []
	refs = {f"C{i + 1}": r for i, r in enumerate(cands)}
	got = call.ask("tidy-backlog", {"request": "Reset: groups of open tasks that can be dealt with in one decision, such as a finished initiative or an idea that went nowhere",
		"items": [{"item": k, "kind": "Task", "title": r.title, "area": r.area_name, "goal": r.goal, "age_days": date_diff(today(), r.touched)}
			for k, r in refs.items()]}, space=space)
	groups = {}
	for d in got.get("decisions") or []:
		if d.get("item") in refs and d.get("decision") in ACTIONS and (d.get("group") or "").strip():
			groups.setdefault((d["group"].strip(), d["decision"]), []).append((refs[d["item"]], d.get("reason") or ""))
	found = []
	for (title, decision), members in groups.items():
		if len(members) < 2 or len(found) == MAX_BATCHES:
			continue
		action, label = ACTIONS[decision]
		batch = _batch(f"ai:{len(found)}", title[:120], members[0][1][:300], [_item("Life Task", r.name, r.title) for r, _reason in members], action, label)
		batch["source"], batch["by"] = "AI", got.label
		found.append(batch)
	return found
