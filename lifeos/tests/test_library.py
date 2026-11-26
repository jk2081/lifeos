"""Tests for library."""
import os
import re
import base64

import frappe
from frappe.utils import add_days, getdate, today

from lifeos import install
from lifeos.library import archive, globalsearch
from lifeos import permissions
from lifeos.ai.tools import Context, t_get_record
from lifeos.api import archive as archive_api, chats, everything, files as files_api, goals as goal_api, graph, inbox, jobs, library, links, search, sources, timeline, today as today_api, vault, wiki
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import find, item, task, upload


def link_rows(doc):
	return frappe.db.sql("select to_doctype, to_name, link_text from `tabLife Link` where from_doctype=%s and from_name=%s order by to_name",
		(doc.doctype, doc.name), as_dict=True)


class TestLinks(LifeTestCase):
	def test_link_is_stored_and_backlink_shows(self):
		target = library.save(space=PRIVATE, title="New crops m7", content_md="pepper")
		source = library.save(space=PRIVATE, title="Training outline m7", content_md="See [[New crops m7]] and [[Does not exist m7]].")
		rows = frappe.get_all("Life Link", filters={"from_name": source["name"]}, fields=["to_doctype", "to_name", "space"])
		self.assertEqual([(r.to_doctype, r.to_name, r.space) for r in rows], [("Life Note", target["name"], PRIVATE)])  # a missing target is not stored
		self.assertEqual([(l["text"], l["title"], l["route"]) for l in source["links"]], [("New crops m7", "New crops m7", f"/library/{target['name']}")])
		back = links.backlinks("Life Note", target["name"])
		self.assertEqual([(b["name"], b["why"]) for b in back], [(source["name"], "links here")])

	def test_links_to_other_record_types(self):
		person = self.make("Life Person", full_name="Ruchi m7")
		task = self.make("Life Task", title="Renew licence m7")
		doc = self.make("Life Vault Document", title="Driving licence m7")
		chat = self.make("Life Chat Log", title="Mandir chat m7", date=today())
		note = self.make("Life Note", title="Hub m7", content_md="[[Ruchi m7]] [[Renew licence m7]] [[Driving licence m7]] [[Mandir chat m7]]")
		self.assertEqual(sorted(r.to_doctype for r in link_rows(note)), ["Life Chat Log", "Life Person", "Life Task", "Life Vault Document"])
		self.assertEqual([b["name"] for b in links.backlinks("Life Person", person.name)], [note.name])
		linked = self.make("Life Task", title="Task with a link m7", notes_md="Needs [[Driving licence m7]]")
		self.assertEqual([(r.to_doctype, r.to_name) for r in link_rows(linked)], [("Life Vault Document", doc.name)])

	def test_rename_updates_link_text(self):
		target = self.make("Life Note", title="Old title m7")
		a = self.make("Life Note", title="Pointer A m7", content_md="Read [[Old title m7]] first. Again: [[Old title m7]].")
		b = self.make("Life Task", title="Pointer B m7", notes_md="[[Old title m7]]")
		target.title = "New title m7"
		target.save()
		a.reload()
		b.reload()
		self.assertEqual(a.content_md, "Read [[New title m7]] first. Again: [[New title m7]].")
		self.assertEqual(b.notes_md, "[[New title m7]]")
		self.assertEqual([r.link_text for r in link_rows(a)], ["New title m7"])
		self.assertEqual(library.get(a.name)["links"][0]["title"], "New title m7")
		self.assertIn("New title m7", frappe.db.get_value("Life Index", {"ref_name": a.name}, "search_text"))

	def test_deleting_a_note_removes_its_links(self):
		target = self.make("Life Note", title="Target m7 del")
		source = self.make("Life Note", title="Source m7 del", content_md="[[Target m7 del]]")
		other = self.make("Life Note", title="Other m7 del", content_md="[[Source m7 del]]")
		self.assertEqual(frappe.db.count("Life Link", {"from_name": source.name}), 1)
		source.delete()
		self.assertEqual(frappe.db.count("Life Link", {"from_name": source.name}), 0)
		self.assertEqual(frappe.db.count("Life Link", {"to_name": source.name}), 0)
		self.assertEqual(links.backlinks("Life Note", target.name), [])

	def test_links_stay_inside_a_space_and_two_titles_ask(self):
		self.make("Life Note", space=SHARED, title="Shared only m7")
		note = self.make("Life Note", title="Private pointer m7", content_md="[[Shared only m7]]")
		self.assertEqual(link_rows(note), [])
		first = self.make("Life Note", title="Twin m7")
		second = self.make("Life Task", title="Twin m7")
		picks = [s for s in links.suggest(space=PRIVATE, text="Twin m7") if s["title"] == "Twin m7"]
		self.assertEqual(len(picks), 2)
		self.assertTrue(all(p["ambiguous"] and p["insert"] == f"[[Twin m7#{p['name']}]]" for p in picks))
		pinned = self.make("Life Note", title="Pinned m7", content_md=f"[[Twin m7#{second.name}]]")
		self.assertEqual([(r.to_doctype, r.to_name) for r in link_rows(pinned)], [("Life Task", second.name)])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, links.suggest, space=PRIVATE, text="Twin")
		self.assertRaises(frappe.PermissionError, links.backlinks, "Life Note", first.name)
		self.assertRaises(frappe.PermissionError, library.get, first.name)

	def test_field_ties_show_as_backlinks(self):
		item = self.make("Life Inbox Item", title="Source item m7")
		task = self.make("Life Task", title="From the item m7", inbox_item=item.name)
		self.assertIn((task.name, "created from this item"), [(b["name"], b["why"]) for b in links.backlinks("Life Inbox Item", item.name)])
		self.assertIn((item.name, "source"), [(b["name"], b["why"]) for b in links.backlinks("Life Task", task.name)])


class TestLibraryAndVault(LifeTestCase):
	def test_note_tree_and_versions(self):
		parent = library.save(space=PRIVATE, title="Parent m7", area=self.areas["Tea"])
		child = library.save(space=PRIVATE, title="Child m7", parent_note=parent["name"], area=self.areas["Tea"], content_md="v1")
		frappe.in_test = False  # Frappe skips version history while tests run
		try:
			library.save(note=child["name"], content_md="v2")
		finally:
			frappe.in_test = True
		tree = library.tree(space=PRIVATE)
		row = next(n for n in tree["notes"] if n["name"] == child["name"])
		self.assertEqual((row["parent_note"], row["area"]), (parent["name"], self.areas["Tea"]))
		self.assertEqual([c["name"] for c in library.get(parent["name"])["children"]], [child["name"]])
		versions = library.versions(child["name"])
		self.assertTrue(versions and versions[0]["previous_content"] == "v1")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, library.tree, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, library.save, note=child["name"], content_md="hacked")

	def test_vault_badges_and_last_four(self):
		person = self.make("Life Person", full_name="Jai m7")
		soon = vault.save(space=PRIVATE, values={"title": "Licence m7", "doc_type": "ID", "holder": person.name, "expiry_date": str(add_days(getdate(today()), 30)),
			"number_last4": "4821", "area": self.areas["Personal"]})
		far = vault.save(space=PRIVATE, values={"title": "Passport m7", "expiry_date": str(add_days(getdate(today()), 400))})
		gone = vault.save(space=PRIVATE, values={"title": "Old policy m7", "expiry_date": str(add_days(getdate(today()), -3)), "remind_days_before": 10})
		self.assertEqual(soon["badge"], {"state": "expiring", "days": 30})
		self.assertIsNone(far["badge"])
		self.assertEqual(gone["badge"], {"state": "expired", "days": -3})
		self.assertRaises(frappe.ValidationError, vault.save, space=PRIVATE, values={"title": "PAN m7", "number_last4": "ABCDE1234F"})
		self.assertRaises(frappe.ValidationError, vault.save, document=soon["name"], values={"owner": "x"})
		data = vault.list(space=PRIVATE)
		group = next(g for g in data["groups"] if g["holder"] == "Jai m7")
		self.assertEqual([d["name"] for d in group["documents"]], [soon["name"]])
		self.assertEqual(data["groups"][-1]["holder"], "No holder")
		from lifeos.api import today as today_api
		self.assertIn(soon["name"], [c["name"] for c in today_api.get(space=PRIVATE)["coming_up"] if c["kind"] == "vault"])

	def test_vault_file_is_private_to_the_space(self):
		from lifeos.tools.devtools import attach
		doc = vault.save(space=PRIVATE, values={"title": "PAN card m7"})
		f = attach("Life Vault Document", doc["name"], "pan-m7.txt", b"scan", "file")
		out = vault.set_file(doc["name"], f.file_url)
		self.assertEqual((out["file"], out["file_name"]), (f.file_url, f.file_name))
		# set 3: an agent reads Vault files only where the space lets agents open the Vault (off by default)
		self.as_user(AGENT)
		self.assertFalse(frappe.get_doc("File", f.name).has_permission("read"))
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertTrue(frappe.get_doc("File", f.name).has_permission("read"))  # the agent can fetch it to send it
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_doc("File", f.name).has_permission("read"))
		self.assertRaises(frappe.PermissionError, vault.get, doc["name"])
		self.assertRaises(frappe.PermissionError, vault.list, space=PRIVATE)


class TestChats(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		for name in frappe.get_all("Life Chat Log", filters={"space": PRIVATE}, pluck="name"):
			frappe.delete_doc("Life Chat Log", name, force=True)
		frappe.set_user(OWNER)
		self.goal = self.make("Life Goal", title="Mandir m7", horizon="Long term", area=self.areas["Tea"])

	def test_agent_logs_a_chat_directly_and_report_groups(self):
		self.as_user(AGENT)
		a = chats.log(space=PRIVATE, title="Mandir budget m7", area="Tea", goal="Mandir m7", summary_md="Sized it", url="https://claude.ai/chat/1",
			open_items=["Decide the deity", "Get two quotes"])["name"]
		b = chats.log(space=PRIVATE, title="ITR papers m7", area="Money", date=str(add_days(getdate(today()), -1)), open_items=["Download statements"], assistant="ChatGPT")["name"]
		c = chats.log(space=PRIVATE, title="No area m7", date=str(add_days(getdate(today()), -2)))["name"]
		chats.log(space=PRIVATE, title="Too old m7", date=str(add_days(getdate(today()), -20)))
		self.assertEqual(frappe.db.get_value("Life Chat Log", a, "owner"), AGENT)
		self.as_user(OWNER)
		seen = {}
		for group_by in ("day", "area", "goal"):
			r = chats.report(space=PRIVATE, group_by=group_by)
			seen[group_by] = sorted(ch["name"] for g in r["groups"] for ch in g["chats"])
			self.assertEqual(r["total"], 3)
			self.assertEqual(len(r["open_items"]), 3)
		self.assertEqual(seen["day"], sorted([a, b, c]))
		self.assertEqual(seen["day"], seen["area"])
		self.assertEqual(seen["day"], seen["goal"])  # the same records under each group_by
		by_area = chats.report(space=PRIVATE, group_by="area")
		self.assertEqual({g["label"]: g["open_items"] for g in by_area["groups"]}, {"Money": 1, "Tea": 2, "No area": 0})
		self.assertEqual(by_area["groups"][-1]["label"], "No area")
		self.assertEqual([g["label"] for g in chats.report(space=PRIVATE, group_by="day")["groups"]],
			[today(), str(add_days(getdate(today()), -1)), str(add_days(getdate(today()), -2))])
		self.assertEqual(chats.report(space=PRIVATE, from_date=add_days(today(), -30), to_date=today())["total"], 4)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, chats.report, space=PRIVATE)

	def test_open_item_becomes_a_task_only_when_a_person_asks(self):
		self.as_user(AGENT)
		name = chats.log(space=PRIVATE, title="Sports setup m7", area="Tea", open_items=["Price a pickleball court", "Find a pavilion design"])["name"]
		row = frappe.get_doc("Life Chat Log", name).open_items
		self.assertEqual(frappe.db.count("Life Task", {"title": "Price a pickleball court"}), 0)
		self.assertRaises(frappe.PermissionError, chats.make_task, name, row[0].name)
		self.as_user(OWNER)
		task = frappe.get_doc("Life Task", chats.make_task(name, row[0].name)["task"])
		self.assertEqual((task.title, task.area), ("Price a pickleball court", self.areas["Tea"]))
		self.assertEqual(chats.make_task(name, row[0].name)["task"], task.name)  # not twice
		chats.close_item(name, row[1].name)
		doc = frappe.get_doc("Life Chat Log", name)
		self.assertEqual([(i.status, i.task) for i in doc.open_items], [("Task Created", task.name), ("Closed", None)])
		self.assertEqual(chats.report(space=PRIVATE)["open_items"], [])
		self.assertIn(task.name, [b["name"] for b in links.backlinks("Life Chat Log", name)])


class TestArchive(LifeTestCase):
	def age(self, doc, field, days):
		frappe.db.set_value(doc.doctype, doc.name, field, add_days(getdate(today()), -days), update_modified=False)

	def test_daily_job_rules(self):
		done_old = self.make("Life Task", title="Done long ago m7", status="Done")
		self.age(done_old, "completed_on", 91)
		dropped_old = self.make("Life Task", title="Dropped long ago m7", status="Dropped")
		self.age(dropped_old, "completed_on", 120)
		done_new = self.make("Life Task", title="Done recently m7", status="Done")
		self.age(done_new, "completed_on", 30)
		stale_open = self.make("Life Task", title="Open and stale m7")
		frappe.db.set_value("Life Task", stale_open.name, {"last_touched_on": add_days(today(), -400), "creation": add_days(today(), -400)}, update_modified=False)
		item_old = self.make("Life Inbox Item", title="Finished item m7", status="Done")
		self.age(item_old, "finished_on", 95)
		item_review = self.make("Life Inbox Item", title="Waiting item m7", status="To Review")
		chat_quiet = self.make("Life Chat Log", title="Quiet chat m7", date=add_days(today(), -100), open_items=[{"text": "x", "status": "Closed"}])
		chat_open = self.make("Life Chat Log", title="Open chat m7", date=add_days(today(), -100), open_items=[{"text": "y", "status": "Open"}])
		vault_doc = self.make("Life Vault Document", title="Expired passport m7", expiry_date=add_days(today(), -900))
		frappe.db.set_value("Life Vault Document", vault_doc.name, "creation", add_days(today(), -900), update_modified=False)
		note = self.make("Life Note", title="Old reference note m7")
		frappe.db.set_value("Life Note", note.name, "creation", add_days(today(), -900), update_modified=False)
		person = self.make("Life Person", full_name="Old friend m7")
		out = archive.run_daily()
		self.assertGreaterEqual(out["Life Task"], 2)

		def state(doc):
			return frappe.db.get_value(doc.doctype, doc.name, ["is_archived", "archive_reason"])

		for doc in (done_old, dropped_old, item_old, chat_quiet):
			self.assertEqual(state(doc), (1, "Auto"), doc.title)
			self.assertEqual(str(frappe.db.get_value(doc.doctype, doc.name, "archived_on")), today())
			self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": doc.name, "kind": ("!=", "Task Done")}, "is_archived"), 1)
		for doc in (done_new, stale_open, item_review, chat_open, vault_doc, note):
			self.assertEqual(state(doc)[0], 0, doc.get("title") or doc.doctype)
		for doc in (done_old, stale_open, vault_doc, note, person):
			self.assertTrue(frappe.db.exists(doc.doctype, doc.name))  # nothing is ever deleted
		# the stale open task is listed under Decide, and the week's archive shows with Undo
		review = today_api.week_summary(space=PRIVATE)
		self.assertIn(stale_open.name, [t["name"] for t in review["decide"]])
		self.assertIn(done_old.name, [a["name"] for a in review["archived"]])
		archive_api.restore("Life Task", done_old.name)
		self.assertEqual(state(done_old), (0, ""))

	def test_archived_records_leave_the_screens_but_stay_on_the_timeline_switch(self):
		task = self.make("Life Task", title="Archive me m7", area=self.areas["Tea"], due_date=today())
		archive_api.set("Life Task", task.name, 1)
		from lifeos.api import tasks
		from lifeos.api import today as today_api
		self.assertNotIn(task.name, [t["name"] for t in tasks.list(space=PRIVATE, page_length=100)["tasks"]])
		self.assertNotIn(task.name, [t["name"] for t in today_api.get(space=PRIVATE)["tasks"]["items"]])
		self.assertNotIn(task.name, [t["name"] for t in tasks.list(space=PRIVATE, area=self.areas["Tea"], page_length=100)["tasks"]])
		self.assertNotIn(task.name, [e["ref_name"] for d in timeline.get(space=PRIVATE, page_length=100)["days"] for e in d["entries"]])
		self.assertIn(task.name, [e["ref_name"] for d in timeline.get(space=PRIVATE, page_length=100, include_archived=1)["days"] for e in d["entries"]])
		listed = archive_api.list(space=PRIVATE)
		group = next(g for g in listed["groups"] if g["area"] == self.areas["Tea"])
		row = next(r for r in group["records"] if r["ref_name"] == task.name)
		self.assertEqual(row["archive_reason"], "Manual")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, archive_api.list, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, archive_api.restore, "Life Task", task.name)

	def test_completing_an_open_goal_archives_its_records_and_restore_brings_them_back(self):
		goal = self.make("Life Goal", title="Finish me m7", horizon="Long term", area=self.areas["Tea"])
		task = self.make("Life Task", title="Goal task m7", area=self.areas["Tea"], goal=goal.name)
		note = self.make("Life Note", title="Goal note m7", area=self.areas["Tea"], goal=goal.name)
		chat = self.make("Life Chat Log", title="Goal chat m7", date=today(), area=self.areas["Tea"], goal=goal.name)
		outside = self.make("Life Task", title="Not under the goal m7", area=self.areas["Tea"])
		already = self.make("Life Note", title="Archived before m7", area=self.areas["Tea"], goal=goal.name, is_archived=1, archive_reason="Manual")
		out = goal_api.set_status(goal.name, "Done")
		self.assertEqual((out["is_archived"], out["archived_records"]), (1, 3))
		for doc in (task, note, chat):
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, ["is_archived", "archive_reason"]), (1, "Project"))
			self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": doc.name}, "is_archived"), 1)
		self.assertEqual(frappe.db.get_value("Life Task", outside.name, "is_archived"), 0)
		self.assertNotIn(goal.name, [g["name"] for g in goal_api.list(space=PRIVATE)["goals"]])
		self.assertNotIn(goal.name, [g["name"] for g in goal_api.list(space=PRIVATE, area=self.areas["Tea"])["goals"]])
		self.assertIn(goal.name, [g["name"] for g in archive_api.list(space=PRIVATE)["goals"]])
		archive_api.restore("Life Goal", goal.name)
		self.assertEqual(frappe.db.get_value("Life Goal", goal.name, ["is_archived", "outcome"]), (0, "In Progress"))
		for doc in (task, note, chat):
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "is_archived"), 0)
			self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": doc.name}, "is_archived"), 0)
		self.assertEqual(frappe.db.get_value("Life Note", already.name, ["is_archived", "archive_reason"]), (1, "Manual"))  # it was archived by hand before
		self.assertIn(goal.name, [g["name"] for g in goal_api.list(space=PRIVATE)["goals"]])


def names(res):
	return [r["ref_name"] for r in res["results"]]


class TestSearch(LifeTestCase):
	def test_finds_a_capture_by_its_title_and_text(self):
		item = inbox.create_item(title="Journal photo Nowrojeezzz m8", source_type="Journal Photo", space=PRIVATE)
		frappe.db.commit()
		res = find("nowrojeezzz", space=PRIVATE)
		self.assertEqual(names(res), [item["name"]])
		self.assertEqual(res["results"][0]["kind"], "Capture")
		self.assertEqual(res["results"][0]["route"], f"/item/{item['name']}")
		self.assertEqual(names(find("nowrojeez", space=PRIVATE)), [item["name"]])  # prefix

	def test_searches_every_filed_type(self):
		made = {
			"note": self.make("Life Note", title="Quartzite note m8", content_md="about zebrafish"),
			"task": self.make("Life Task", title="Quartzite task m8"),
			"chat": self.make("Life Chat Log", title="Quartzite chat m8", date=today(), summary_md="s"),
			"vault": self.make("Life Vault Document", title="Quartzite passport m8"),
			"page": self.make("Life Note", title="Journal page m8", page_date=today(), content_md="quartzite on the page"),
		}
		frappe.db.commit()
		got = names(find("quartzite"))
		for doc in made.values():
			self.assertIn(doc.name, got)
		self.assertEqual(names(find("zebrafish")), [made["note"].name])
		self.assertEqual(names(find("quartzite zebrafish")), [made["note"].name])  # every word must match
		self.assertEqual(names(find("m8 xyznotthere")), [])
		self.assertEqual(find("   ")["results"], [])
		self.assertLessEqual(len(find("quartzite", limit=2)["results"]), 2)

	def test_outsider_finds_nothing_from_a_private_space(self):
		secret = self.make("Life Note", title="Obsidianite secret m8", content_md="obsidianite plans")
		shared = self.make("Life Note", space=SHARED, title="Obsidianite shopping m8")
		frappe.db.commit()
		self.assertEqual(sorted(names(find("obsidianite"))), sorted([secret.name, shared.name]))
		self.as_user(FAMILY)
		self.assertEqual(names(find("obsidianite")), [shared.name])
		self.assertRaises(frappe.PermissionError, search.query, "obsidianite", space=PRIVATE)
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, search.query, "obsidianite")

	def test_archived_records_are_hidden_unless_asked(self):
		note = self.make("Life Note", title="Feldsparite archived m8", is_archived=1)
		frappe.db.commit()
		self.assertEqual(names(find("feldsparite")), [])
		self.assertEqual(names(find("feldsparite", include_archived=1)), [note.name])

	def test_short_and_odd_words_fall_back(self):
		note = self.make("Life Note", title="ZQ m8 pan", content_md="x")
		frappe.db.commit()
		self.assertIn(note.name, names(find("zq")))
		self.assertEqual(find("+-*()\"")["results"], [])


class TestGraph(LifeTestCase):
	def test_nodes_and_edges(self):
		person = self.make("Life Person", full_name="Ruchi m8")
		target = self.make("Life Note", title="Graph target m8")
		source = self.make("Life Note", title="Graph source m8", content_md="[[Graph target m8]] and [[Ruchi m8]]", parent_note=target.name)
		doc = self.make("Life Vault Document", title="Passport graph m8", holder=person.name)
		cycle = self.make("Life Cycle", title="Graph cycle", start_date=today())
		goal = self.make("Life Goal", cycle=cycle.name, title="Graph goal m8")
		lonely = self.make("Life Note", title="Lonely m8")
		far = self.make("Life Note", title="Far m8", content_md="[[Lonely m8]]")
		data = graph.get(space=PRIVATE)
		ids = {n["id"]: n for n in data["nodes"]}
		for dt, d, kind in (("Life Note", source, "Note"), ("Life Note", target, "Note"), ("Life Person", person, "Person"),
				("Life Vault Document", doc, "Document"), ("Life Goal", goal, "Goal")):
			self.assertEqual(ids[f"{dt}/{d.name}"]["type"], kind)
		pairs = {(e["source"], e["target"], e["kind"]) for e in data["edges"]}
		self.assertIn((f"Life Note/{source.name}", f"Life Note/{target.name}", "link"), pairs)
		self.assertIn((f"Life Note/{source.name}", f"Life Person/{person.name}", "link"), pairs)
		self.assertIn((f"Life Note/{source.name}", f"Life Note/{target.name}", "parent"), pairs)
		self.assertIn((f"Life Vault Document/{doc.name}", f"Life Person/{person.name}", "holder"), pairs)
		self.assertEqual(ids[f"Life Note/{target.name}"]["route"], f"/library/{target.name}")
		# two steps around one record
		near = graph.get(space=PRIVATE, center=f"Life Note/{target.name}")
		near_ids = {n["id"] for n in near["nodes"]}
		self.assertEqual(near_ids, {f"Life Note/{target.name}", f"Life Note/{source.name}", f"Life Person/{person.name}"})
		self.assertNotIn(f"Life Vault Document/{doc.name}", near_ids)  # three steps away
		self.assertNotIn(f"Life Note/{far.name}", near_ids)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, graph.get, space=PRIVATE)
		shared = graph.get(space=SHARED)
		self.assertNotIn(f"Life Note/{target.name}", [n["id"] for n in shared["nodes"]])


class TestEverything(LifeTestCase):
	def setUp(self):
		super().setUp()
		for dt in ("Life Note", "Life Vault Document", "Life Chat Log", "Life Person"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.delete("Life Index", {"space": PRIVATE})
		self.career = self.life["Career"]
		self.note = self.make("Life Note", title="i23 plain note", content_md="the zebrafruit idea", area=self.career).name
		self.wiki = self.make("Life Note", title="i23 Mehi Motors", collection="Wiki", summary="Organisation · Honda dealer", content_md="x").name
		self.page = self.make("Life Note", title="i23 wiki page", collection="Wiki", summary="A concept", content_md="x").name
		self.doc = self.make("Life Vault Document", title="i23 passport", doc_type="ID").name
		self.chat = self.make("Life Chat Log", title="i23 chat", assistant="Claude", date="2026-11-18", summary_md="s",
			open_items=[{"text": "do it", "status": "Open"}]).name
		self.person = self.make("Life Person", full_name="i23 Mr Rao", relation="Manager").name

	def refs(self, **kw):
		return [r["ref"] for r in everything.list(space=PRIVATE, **kw)["rows"]]

	def test_everything_shows_each_kind_with_its_letter_and_line(self):
		rows = {r["ref"]: r for r in everything.list(space=PRIVATE)["rows"]}
		self.assertEqual(rows["note:" + self.note]["letter"], "N")
		self.assertEqual(rows["note:" + self.wiki]["letter"], "P")
		self.assertIn("kept by the Brain", rows["note:" + self.wiki]["line"])
		self.assertEqual(rows["note:" + self.page]["letter"], "N")
		self.assertEqual(rows["vault:" + self.doc]["letter"], "D")
		self.assertIn("sensitive", rows["vault:" + self.doc]["line"])
		self.assertEqual(rows["chat:" + self.chat]["letter"], "C")
		self.assertEqual(rows["chat:" + self.chat]["line"], "Chat · Claude · 1 open item")
		self.assertEqual(rows["person:" + self.person]["line"], "Person · Manager")
		dates = [r["date"] for r in everything.list(space=PRIVATE)["rows"]]
		self.assertEqual(dates, sorted(dates, reverse=True))

	def test_each_tab_holds_only_its_kind(self):
		for tab, letter in (("notes", "N"), ("documents", "D"), ("people", "P"), ("chats", "C")):
			rows = everything.list(space=PRIVATE, tab=tab)["rows"]
			self.assertTrue(rows, tab)
			self.assertEqual({r["letter"] for r in rows}, {letter}, tab)
		self.assertIn("person:" + self.person, self.refs(tab="people"))
		self.assertIn("note:" + self.wiki, self.refs(tab="people"))
		self.assertNotIn("note:" + self.wiki, self.refs(tab="notes"))

	def test_search_finds_a_word_in_the_body_and_the_area_filter_narrows(self):
		self.assertEqual(self.refs(q="zebrafruit"), ["note:" + self.note])
		self.assertEqual(self.refs(q="50% off_"), [])
		self.assertEqual(self.refs(area=self.career), ["note:" + self.note])
		self.assertEqual(everything.list(space=PRIVATE, q="zebrafruit", area=self.life["Health"])["total"], 0)

	def test_a_closed_vault_hides_the_sensitive_document(self):
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.assertIn("vault:" + self.doc, self.refs())
		self.as_user(AGENT)
		self.assertNotIn("vault:" + self.doc, self.refs())
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertIn("vault:" + self.doc, self.refs())
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)

	def test_a_bad_tab_is_refused(self):
		self.assertRaises(frappe.ValidationError, everything.list, space=PRIVATE, tab="nope")


SLIDES = b"issue 24 slides"


class TestFilesList(LifeTestCase):
	def rows(self, **kw):
		return files_api.list(space=PRIVATE, **kw)["rows"]

	def by_name(self, name, **kw):
		return [r for r in self.rows(**kw) if r["name"] == name]

	def test_1_a_file_used_by_two_items_is_listed_once_with_both(self):
		a, b = item("i24 first user"), item("i24 second user")
		upload("Life Inbox Item", a, "i24 shared deck.pptx", SLIDES)
		upload("Life Inbox Item", b, "i24 shared deck.pptx", SLIDES)
		got = self.by_name("i24 shared deck.pptx")
		self.assertEqual(len(got), 1)
		self.assertEqual({u["name"] for u in got[0]["used_in"]}, {a, b})
		self.assertEqual(files_api.list(space=PRIVATE, q="i24 shared")["total"], 1)

	def test_2_a_file_with_two_versions_lists_both(self):
		it = item("i24 versions", external_id="i24-versions", source_system="claude")
		upload("Life Inbox Item", it, "i24 report.txt", b"one")
		upload("Life Inbox Item", it, "i24 report.txt", b"two, newer")
		got = self.by_name("i24 report.txt")
		self.assertEqual(len(got), 1)
		self.assertEqual(got[0]["version_count"], 2)
		self.assertEqual(len({v["url"] for v in got[0]["versions"]}), 2)
		self.assertTrue(got[0]["versions"][0]["current"] and got[0]["versions"][0]["url"] == got[0]["url"])

	def test_3_the_type_filter_holds_only_that_type(self):
		it = item("i24 types")
		for n, b in (("i24 a.pptx", b"s"), ("i24 b.txt", b"d"), ("i24 c.png", b"i"), ("i24 d.mp3", b"a")):
			upload("Life Inbox Item", it, n, b)
		for t, n in (("slides", "i24 a.pptx"), ("documents", "i24 b.txt"), ("images", "i24 c.png"), ("audio", "i24 d.mp3")):
			names = [r["name"] for r in self.rows(type=t)]
			self.assertIn(n, names)
			self.assertTrue(all(files_api.file_type(x) == t for x in names), (t, names))
		self.assertRaises(frappe.ValidationError, files_api.list, space=PRIVATE, type="video")

	def test_4_a_file_only_a_closed_vault_document_uses_is_not_listed_for_the_agent(self):
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		doc = self.make("Life Vault Document", title="i24 passport", doc_type="ID").name
		upload("Life Vault Document", doc, "i24 passport.txt", b"passport")
		it = item("i24 plain")
		upload("Life Inbox Item", it, "i24 both.txt", b"both")
		upload("Life Vault Document", doc, "i24 both.txt", b"both")
		self.assertEqual(len(self.by_name("i24 passport.txt")), 1)
		self.as_user(AGENT)
		self.assertEqual(self.by_name("i24 passport.txt"), [])
		both = self.by_name("i24 both.txt")
		self.assertEqual([u["name"] for u in both[0]["used_in"]], [it])

	def test_5_a_user_outside_the_space_cannot_list_its_files(self):
		upload("Life Inbox Item", item("i24 private"), "i24 private.txt", b"private")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, files_api.list, space=PRIVATE)

	def test_6_a_reusable_asset_shows_how_many_jobs_used_it(self):
		inputs = [{"name": "i24 BTW deck.txt", "file": base64.b64encode(b"i24 btw deck").decode(), "reusable_as": "i24-btw-deck"}]
		for k in (1, 2):
			jobs.file_job(job_id=f"i24-job-{k}", space=PRIVATE, title=f"i24 job {k}", raw_text="x", inputs=inputs, outputs=[])
		got = self.by_name("i24 BTW deck.txt")
		self.assertEqual(len(got), 1)
		self.assertTrue(got[0]["reusable"])
		self.assertEqual(got[0]["jobs"], 2)

	def test_7_the_area_and_source_filters_narrow_the_list(self):
		it = item("i24 area", area=self.life["Career"])
		upload("Life Inbox Item", it, "i24 career.txt", b"career")
		upload("Life Inbox Item", item("i24 no area"), "i24 loose.txt", b"loose")
		self.assertEqual([r["name"] for r in self.rows(area=self.life["Career"], q="i24 ")], ["i24 career.txt"])
		self.assertEqual([r["name"] for r in self.rows(area="none", q="i24 loose")], ["i24 loose.txt"])
		self.assertEqual(len(self.rows(source="brain", q="i24 career")), 0)


def set_switch(space, field, on):
	frappe.set_user("Administrator")
	frappe.db.set_value("Life Space", space, field, 1 if on else 0)
	permissions.clear_cache()


class TestSensitive(LifeTestCase):
	def tearDown(self):
		set_switch(SHARED, "agents_can_read_vault", 0)
		set_switch(SHARED, "ask_can_read_vault", 0)
		super().tearDown()

	def test_agent_cannot_open_a_sensitive_note_while_the_switch_is_off(self):
		note = self.make("Life Note", space=SHARED, title="ux6 secret note", content_md="kumquatsecret", area=self.shared_areas["Family"])
		library.set_sensitive("Life Note", note.name, 1)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, permissions.get_doc_checked, "Life Note", note.name)
		self.assertNotIn(note.name, [r.name for r in library.list(space=SHARED, collection="all", page_length=100)["notes"]])
		self.assertFalse([r for r in find(text="kumquatsecret", space=SHARED)["results"] if r.ref_name == note.name])
		set_switch(SHARED, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertEqual(permissions.get_doc_checked("Life Note", note.name).name, note.name)

	def test_agent_does_not_claim_or_list_a_sensitive_inbox_item(self):
		item = self.make("Life Inbox Item", space=SHARED, title="ux6 sensitive capture", status="To Review", is_sensitive=1)
		self.as_user(AGENT)
		self.assertNotIn(item.name, [r.name for r in inbox.list(space=SHARED, page_length=100)["items"]])
		self.assertNotIn(item.name, [r["name"] for r in sources.list(space=SHARED, page_length=100)["sources"]])
		self.assertFalse(frappe.get_list("Life Inbox Item", filters={"name": item.name}))

	def test_only_the_owner_can_unmark(self):
		note = self.make("Life Note", space=SHARED, title="ux6 family note", content_md="x")
		self.as_user(FAMILY)
		library.set_sensitive("Life Note", note.name, 1)  # anyone who may edit can mark
		self.assertRaises(frappe.PermissionError, library.set_sensitive, "Life Note", note.name, 0)
		self.as_user(OWNER)
		self.assertEqual(library.set_sensitive("Life Note", note.name, 0)["is_sensitive"], 0)

	def test_agents_cannot_mark(self):
		note = self.make("Life Note", space=PRIVATE, title="ux6 agent mark", content_md="x")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, library.set_sensitive, "Life Note", note.name, 1)

	def test_ask_reads_a_sensitive_item_only_with_its_switch(self):
		note = self.make("Life Note", space=SHARED, title="ux6 ask note", content_md="private words", is_sensitive=1)
		ctx = Context(SHARED, {"kind": "space"}, user=OWNER)
		self.assertIn("error", t_get_record(ctx, doctype="Life Note", name=note.name))
		set_switch(SHARED, "ask_can_read_vault", 1)
		self.as_user(OWNER)
		ctx = Context(SHARED, {"kind": "space"}, user=OWNER)
		self.assertNotIn("error", t_get_record(ctx, doctype="Life Note", name=note.name))

	def test_a_sensitive_wiki_page_is_hidden_from_the_agent(self):
		frappe.flags.lifeos_wiki_api = True
		try:
			page = self.make("Life Note", space=SHARED, title="ux6 wiki secret", collection="Wiki", summary="s", content_md="x")
		finally:
			frappe.flags.lifeos_wiki_api = False
		library.set_sensitive("Life Note", page.name, 1)
		self.as_user(AGENT)
		self.assertNotIn(page.name, [r.name for r in wiki.index(space=SHARED, page_length=500)["pages"]])


class TestCaptures(LifeTestCase):
	def test_vault_documents_are_sensitive_documents_with_their_expiry(self):
		person = self.make("Life Person", full_name="ux6 Holder")
		doc = self.make("Life Vault Document", title="ux6 passport", doc_type="Travel", holder=person.name, number_last4="1234",
			issue_date=add_days(today(), -300), expiry_date=add_days(today(), 20), remind_days_before=60)
		res = sources.list(space=PRIVATE, tab="documents", page_length=100)
		row = next(r for r in res["sources"] if r["name"] == doc.name)
		self.assertEqual((row["kind"], row["sensitive"], row["holder_name"], row["number_last4"]), ("Document", 1, "ux6 Holder", "1234"))
		self.assertEqual(row["expiry"]["state"], "expiring")
		self.assertEqual(row["ref"], "vault:" + doc.name)
		self.assertIn(doc.name, [r["name"] for r in sources.list(space=PRIVATE, sensitive=1, page_length=100)["sources"]])

	def test_all_holds_notes_and_written_by(self):
		mine = self.make("Life Note", title="ux6 my note", content_md="x")
		frappe.flags.lifeos_wiki_api = True
		try:
			kept = self.make("Life Note", title="ux6 kept note", collection="Wiki", summary="s", content_md="x")
		finally:
			frappe.flags.lifeos_wiki_api = False
		everything = [r["name"] for r in sources.list(space=PRIVATE, scope="all", tab="notes", page_length=100)["sources"]]
		self.assertIn(mine.name, everything)
		self.assertIn(kept.name, everything)
		by_assistant = sources.list(space=PRIVATE, scope="all", tab="notes", by="assistant", page_length=100)["sources"]
		self.assertEqual({r["name"] for r in by_assistant} & {mine.name, kept.name}, {kept.name})
		self.assertTrue(next(r for r in by_assistant if r["name"] == kept.name)["by_assistant"])
		self.assertNotIn("notes", sources.list(space=PRIVATE, page_length=1)["tabs"])
		self.assertEqual({r.name for r in library.list(space=PRIVATE, collection="all", page_length=200)["notes"]} & {mine.name, kept.name},
			{mine.name, kept.name})


class TestSensitiveEverywhere(LifeTestCase):
	"""The review of set 6: every agent read leaves sensitive items out while the space's switch is off."""

	def test_agent_reads_leave_sensitive_items_out(self):
		from frappe.utils import today as day

		from lifeos.api import chats, goals, links
		from lifeos.api import today as today_api

		goal = self.make("Life Goal", space=SHARED, title="ux6 review goal", horizon="Long term")
		parent = self.make("Life Note", space=SHARED, title="ux6 parent", content_md="x", goal=goal.name)
		child = self.make("Life Note", space=SHARED, title="ux6 secret child", content_md="x", parent_note=parent.name, goal=goal.name, is_sensitive=1)
		item = self.make("Life Inbox Item", space=SHARED, title="ux6 secret item", status="To Review", is_sensitive=1)
		chat = self.make("Life Chat Log", space=SHARED, title="ux6 secret chat", date=day(), is_sensitive=1)
		self.as_user(AGENT)
		self.assertNotIn(child.name, [c.name for c in library.get(parent.name)["children"]])
		self.assertNotIn(child.name, [r["name"] for r in links.backlinks("Life Goal", goal.name)])
		self.assertNotIn(item.name, [r.name for r in today_api.get(space=SHARED)["to_review"]["items"]])
		self.assertNotIn(chat.name, [c["name"] for g in chats.report(space=SHARED)["groups"] for c in g["chats"]])
		self.assertRaises(frappe.PermissionError, library.get, child.name)
		self.assertIsNotNone(goals)

	def test_agent_cannot_mark_through_a_plain_save(self):
		note = self.make("Life Note", space=SHARED, title="ux6 agent save", content_md="x")
		self.as_user(AGENT)
		doc = frappe.get_doc("Life Note", note.name)
		doc.is_sensitive = 1
		self.assertRaises(frappe.PermissionError, doc.save)


class TestScreenFolders(LifeTestCase):
	"""The item, Brain and Library screens reach the server through frontend/src/data/{item,brain,library}.js (#80)."""

	SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "src")

	def test_no_screen_file_calls_api_directly(self):
		bad = []
		for folder in ("components/item", "components/brain", "components/library"):
			path = os.path.join(self.SRC, folder)
			for name in sorted(os.listdir(path)):
				if not name.endswith((".vue", ".js")):
					continue
				source = open(os.path.join(path, name), encoding="utf-8").read()
				if re.search(r"\bapi\(", source) or re.search(r"import\s*\{[^}]*\bapi\b[^}]*\}\s*from\s*'@/lib/api'", source):
					bad.append(f"{folder}/{name}")
		page = open(os.path.join(self.SRC, "pages", "Item.vue"), encoding="utf-8").read()
		if re.search(r"\bapi\(", page):
			bad.append("pages/Item.vue")
		self.assertEqual(bad, [], "these call api( directly; use data/item.js, brain.js or library.js")

	def test_the_pane_has_one_item_view(self):
		self.assertNotIn("pane", os.listdir(os.path.join(self.SRC, "components")))
		item = os.listdir(os.path.join(self.SRC, "components", "item"))
		self.assertNotIn("RecordPane.vue", item)
		self.assertNotIn("PaneBody.vue", item)
		self.assertIn("ItemView.vue", item)


def titles(res):
	return [r["title"] for r in res["results"]]


class TestGlobalSearch(LifeTestCase):
	"""Issue 98: search reads Frappe's Global Search, and every hit passes our space rules."""

	def event(self, subject, space=PRIVATE, **values):
		return frappe.get_doc({"doctype": "Event", "subject": subject, "starts_on": f"{today()} 10:00:00", "life_space": space, **values}).insert()

	def test_1_an_event_is_found_by_the_start_of_any_word(self):
		event = self.event("RSH Global meeting q98")
		for word in ("rsh", "global", "RSH glob", "q98"):
			res = find(word, space=PRIVATE)
			self.assertEqual(names(res), [event.name], word)
		hit = find("rsh")["results"][0]
		self.assertEqual((hit["kind"], hit["group"], hit["title"], hit["record_date"]), ("Event", "Events", "RSH Global meeting q98", today()))
		self.assertEqual(hit["route"], f"/today?open=event:{event.name}")
		self.assertEqual(find("rsh xyznotthere")["results"], [])

	def test_2_an_event_in_a_space_the_user_cannot_read_is_not_returned(self):
		event = self.event("Zebra board q98")
		self.assertEqual(names(find("zebra")), [event.name])
		self.as_user(FAMILY)
		self.assertEqual(find("zebra")["results"], [])
		self.assertTrue(frappe.db.exists("__global_search", {"doctype": "Event", "name": event.name}))

	def test_3_a_vault_document_is_found_by_its_title_only(self):
		doc = self.make("Life Vault Document", title="Passport quillfeather q98", notes_md="contentsecret98 inside")
		self.assertEqual(names(find("quillfeather")), [doc.name])
		self.assertEqual(names(find("contentsecret98")), [])
		self.assertEqual(find("quillfeather")["results"][0]["snippet"], "")

	def test_4_a_goal_an_area_part_a_person_and_a_habit_are_found_by_name(self):
		from lifeos.tools import seed
		part = seed.make_areas(PRIVATE, ["BTWq98"])["BTWq98"]
		goal = self.make("Life Goal", title="Grandgoal q98", horizon="Long term", area=part)
		person = self.make("Life Person", full_name="Pernilla q98", aliases="Nilla98")
		habit = self.make("Life Habit", title="Walkaround q98")
		for word, doctype, name in (("btwq98", "Life Area", part), ("grandgoal", "Life Goal", goal.name), ("pernilla", "Life Person", person.name),
				("nilla98", "Life Person", person.name), ("walkaround", "Life Habit", habit.name)):
			got = [(r["ref_doctype"], r["ref_name"]) for r in find(word)["results"]]
			self.assertIn((doctype, name), got, word)

	def test_5_a_comment_finds_the_record_it_is_on(self):
		event = self.event("Dinner q98")
		event.add_comment("Comment", "send gift98 to Anya")
		res = find("send gift98")
		self.assertEqual([(r["ref_doctype"], r["ref_name"], r["kind"]) for r in res["results"]], [("Event", event.name, "Event")])
		self.assertIn("gift98", res["results"][0]["snippet"])
		self.as_user(FAMILY)
		self.assertEqual(find("gift98")["results"], [])

	def test_6_system_records_are_never_returned(self):
		from frappe.utils.global_search import sync_value
		usage = frappe.get_doc({"doctype": "Life AI Usage", "user": OWNER, "month": "2026-11", "model": "m", "cost": 1, "purpose": "Ask sysrow98"}).insert(ignore_permissions=True)
		log = frappe.get_all("Life Action Log", pluck="name", limit=1)
		for doctype, name in [("Life AI Usage", usage.name), *([("Life Action Log", log[0])] if log else [])]:
			sync_value({"doctype": doctype, "name": name, "content": "Purpose : sysrow98", "published": 0, "title": "sysrow98", "route": ""})
		self.assertEqual(find("sysrow98")["results"], [])
		self.assertTrue(frappe.db.exists("__global_search", {"doctype": "Life AI Usage", "name": usage.name}))
		for dt in ("Life AI Usage", "Life AI Price", "Life Action Log", "Life Agent Action", "Life Agent Job", "Life Skill Run", "Life Settings", "Life Index"):
			self.assertNotIn(dt, globalsearch.FIELDS)

	def test_7_an_archived_record_and_another_space_follow_the_filters(self):
		note = self.make("Life Note", title="Archivalx q98", is_archived=1)
		self.assertEqual(names(find("archivalx")), [])
		self.assertEqual(names(find("archivalx", include_archived=1)), [note.name])
		self.assertEqual(names(find("archivalx", space=SHARED, include_archived=1)), [])

	def test_10_a_fresh_install_lists_the_record_types(self):
		frappe.db.delete("Global Search DocType")
		for dt in globalsearch.FIELDS:
			frappe.db.delete("Property Setter", {"doc_type": dt, "property": "in_global_search"})
			frappe.clear_cache(doctype=dt)
		install.setup()
		listed = set(frappe.get_all("Global Search DocType", pluck="document_type"))
		self.assertEqual(listed, {dt for dt in globalsearch.FIELDS if frappe.get_meta(dt).module != "Core"})
		self.assertTrue({"Event", "Life Goal", "Life Person", "Life Habit", "Life Area", "Life Vault Document", "Life Task"} <= listed)
		for dt, (_kind, fields) in globalsearch.FIELDS.items():
			self.assertEqual(sorted(f.fieldname for f in frappe.get_meta(dt).get_global_search_fields()), sorted(fields), dt)


# ---------------------------------------------------------------- pages that build themselves (issue 111)
import json

from lifeos.ai import client as ai_client
from lifeos.api import pages as pages_api, review as review_api
from lifeos.library import briefs, pins as pins_lib, subjects
from lifeos.tests.helpers import AskCase
from lifeos.tools import actions


def say(obj):
	return {"content": [{"type": "text", "text": json.dumps(obj)}], "stop_reason": "end_turn"}


def who(**kw):
	return say({"context": "business", "person": "Anirudh Poddar", "role": "", "organisation": "", "same_as": "", "unsure_of": "", "reason": "x", **kw})


def mail(n, address="anirudh@sap-partner.example", name="Anirudh Poddar", **kw):
	return {"thread_id": f"thread-{n}", "address": address, "sender_name": name, "subject": f"Blueprint {n}", "text": f"Message {n} about the blueprint.", "signature": "Anirudh, SAP Partner Pvt Ltd",
		"replied": False, "bulk": False, "url": f"https://mail.example/{n}", **kw}


class TestPages(AskCase):
	def setUp(self):
		super().setUp()
		for dt in ("Life Sender Sighting", "Life Pin", "Life Page Visit"):
			frappe.db.delete(dt)
		frappe.db.delete("Life Link", {"origin": ("in", ("Brain", "Owner"))})
		frappe.db.delete("Life Skill Correction", {"skill": "link-subjects"})
		frappe.db.delete("Life Agent Action", {"agent": subjects.BRAIN})
		frappe.db.delete("Life Proposal", {"kind": ("in", ("New Subject", "Same Subject"))})

	def person(self, name, **kw):
		return self.make("Life Person", full_name=name, space=PRIVATE, **kw)

	def test_1_a_filed_email_from_a_known_person_is_linked_to_them_and_their_organisation(self):
		org = self.person("Ambaji Foods q111", kind="Organisation")
		anirudh = self.person("Anirudh q111", email="anirudh@ambaji.example", organisation=org.name)
		it = inbox.create_item(title="Blueprint email q111", source_type="Email", space=PRIVATE, raw_text="The blueprint is attached.")["name"]
		got = subjects.see_email(PRIVATE, mail(1, "anirudh@ambaji.example", "Anirudh q111"), it)
		self.assertEqual({n for _d, n in got["linked"]}, {anirudh.name, org.name})
		line, total = subjects.timeline("Life Person", org.name)
		self.assertEqual(total, 1)
		self.assertEqual((line[0]["kind"], line[0]["title"]), ("Email", "Blueprint email q111"))

	def test_2_a_reply_thread_with_a_new_sender_makes_a_person_and_a_company_and_undo_removes_both(self):
		self.script(who(organisation="SAP Partner Pvt Ltd", role="Solutions Lead"))
		got = subjects.see_email(PRIVATE, mail(2, replied=True))
		self.assertEqual(len(got["made"]), 2)
		person = frappe.db.get_value("Life Person", {"space": PRIVATE, "email": "anirudh@sap-partner.example"}, ["name", "organisation", "kind"], as_dict=True)
		self.assertEqual(frappe.db.get_value("Life Person", person.organisation, "full_name"), "SAP Partner Pvt Ltd")
		self.assertEqual(frappe.db.get_value("Life Person", person.organisation, "kind"), "Organisation")
		row = frappe.get_all("Life Agent Action", filters={"agent": subjects.BRAIN, "action": "subjects.make"}, fields=["name", "undone"])
		self.assertEqual(len(row), 1)
		self.assertEqual(subjects.timeline("Life Person", person.organisation)[1], 1)
		actions.undo(row[0].name)
		self.assertFalse(frappe.db.exists("Life Person", person.name))
		self.assertFalse(frappe.db.exists("Life Person", person.organisation))
		self.assertFalse(frappe.db.exists("Life Link", {"to_name": ("in", [person.name, person.organisation])}))

	def test_3_three_emails_without_a_reply_make_one_proposal_not_a_page(self):
		self.script(who(organisation="SAP Partner Pvt Ltd"))
		for n in (3, 4, 5):
			got = subjects.see_email(PRIVATE, mail(n))
		self.assertTrue(got["proposed"])
		self.assertEqual(frappe.db.count("Life Person", {"space": PRIVATE, "email": "anirudh@sap-partner.example"}), 0)
		subjects.see_email(PRIVATE, mail(6))  # asked once
		props = frappe.get_all("Life Proposal", filters={"kind": "New Subject", "space": PRIVATE, "status": "Pending"}, fields=["name", "preview"])
		self.assertEqual([p.preview for p in props], ["New company: SAP Partner Pvt Ltd. Make a page?"])
		review_api.decide(props[0].name, "accept")
		org = frappe.db.get_value("Life Person", {"space": PRIVATE, "full_name": "SAP Partner Pvt Ltd"})
		self.assertTrue(org)
		line, total = subjects.timeline("Life Person", org)
		self.assertGreaterEqual(total, 3)
		self.assertTrue({"Blueprint 3", "Blueprint 4", "Blueprint 5"} <= {e["title"] for e in line})

	def test_4_a_promotion_makes_no_subject(self):
		before = frappe.db.count("Life Person", {"space": PRIVATE})
		for n in (7, 8, 9, 10):
			got = subjects.see_email(PRIVATE, mail(n, "deals@shop.example", "Shop", bulk=True))
		self.assertEqual(got["made"], [])
		self.assertEqual(frappe.db.count("Life Person", {"space": PRIVATE}), before)
		self.assertEqual(frappe.db.count("Life Proposal", {"kind": "New Subject", "space": PRIVATE}), 0)

	def test_5_same_company_merges_adds_the_alias_and_links_later_mail(self):
		ambaji = self.person("Shri Ambaji Food Products", kind="Organisation")
		self.script(who(organisation="Shakambhari Foods", unsure_of="Shri Ambaji Food Products", person="Hari"))
		got = subjects.see_email(PRIVATE, mail(11, "hari@shak.example", "Hari", replied=True))
		self.assertTrue(got["asked"])
		prop = frappe.get_doc("Life Proposal", got["asked"])
		self.assertEqual(prop.preview, "Is Shakambhari Foods the same as Shri Ambaji Food Products?")
		shak = self.person("Shakambhari Foods", kind="Organisation")  # made meanwhile: the answer joins the two
		old = item("Old email q111", raw_text="x")
		subjects.link(PRIVATE, "Life Inbox Item", old, "Life Person", shak.name)
		review_api.decide(prop.name, "accept")
		self.assertFalse(frappe.db.exists("Life Person", shak.name))
		self.assertIn("Shakambhari Foods", subjects.split_aliases(frappe.db.get_value("Life Person", ambaji.name, "aliases")))
		self.assertIn("Old email q111", [e["title"] for e in subjects.timeline("Life Person", ambaji.name)[0]])
		later = subjects.see_email(PRIVATE, mail(12, "other@elsewhere.example", "Someone", text="Regards from Shakambhari Foods", replied=True))
		self.assertIn(("Life Person", ambaji.name), later["linked"])

	def linked_item(self, subject, title, **kw):
		it = item(title, raw_text=kw.pop("raw_text", "Some text about it."), **kw)
		subjects.link(PRIVATE, "Life Inbox Item", it, "Life Person", subject.name)
		return it

	def test_6_the_daily_job_rewrites_only_subjects_with_something_new_and_never_reads_a_vault_item(self):
		a, b = self.person("Brief A q111", kind="Organisation"), self.person("Brief B q111", kind="Organisation")
		one = self.linked_item(a, "Quote for tea q111", raw_text="The quote is 4.2 lakh for tea.")
		secret = self.linked_item(a, "Passport scan q111", raw_text="passport-secret-text")
		frappe.db.set_value("Life Inbox Item", secret, "is_sensitive", 1)
		self.linked_item(b, "Hello q111")
		frappe.db.set_value("Life Person", b.name, "brief_on", frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=1))  # written after the last link: nothing new
		model = self.script(say({"sentences": [{"text": "They asked for a quote of 4.2 lakh.", "sources": [1]}, {"text": "Nothing cited.", "sources": []}]}))
		briefs.run_daily()
		brief = briefs.read("Life Person", a.name)
		self.assertIn("They asked for a quote of 4.2 lakh. [1]", brief["md"])
		self.assertNotIn("Nothing cited", brief["md"])
		self.assertIn("1 sensitive document", brief["md"])
		self.assertEqual([(s["doctype"], s["name"]) for s in brief["sources"]], [("Life Inbox Item", one)])
		self.assertIsNone(briefs.read("Life Person", b.name))
		self.assertEqual(len(model.received), 1)
		self.assertNotIn("passport-secret-text", json.dumps(model.received))
		self.assertFalse(briefs.stale("Life Person", a.name))
		self.linked_item(a, "Another q111")
		self.assertTrue(briefs.stale("Life Person", a.name))
		briefs.run_daily()  # not again on the same day
		self.assertEqual(len(model.received), 1)

	def test_7_a_brief_is_counted_in_ai_usage_and_skipped_at_the_cap(self):
		a = self.person("Brief C q111", kind="Organisation")
		self.linked_item(a, "Quote q111")
		self.script(say({"sentences": [{"text": "A quote came.", "sources": [1]}]}))
		self.assertTrue(briefs.rewrite("Life Person", a.name)["written"])
		self.assertEqual(frappe.db.count("Life AI Usage", {"purpose": "Skill: write-brief"}), 1)
		self.linked_item(a, "More q111")
		frappe.db.set_single_value("Life Settings", "monthly_cap_usd", 0.000001)
		frappe.clear_cache(doctype="Life Settings")
		try:
			frappe.db.set_value("Life Person", a.name, "brief_on", frappe.utils.add_days(frappe.utils.now_datetime(), -2))
			res = briefs.rewrite("Life Person", a.name)
			self.assertFalse(res["written"])
			self.assertTrue(res.get("capped"))
			self.assertEqual(frappe.db.count("Life AI Usage", {"purpose": "Skill: write-brief"}), 1)
		finally:
			frappe.db.set_single_value("Life Settings", "monthly_cap_usd", 30)
			frappe.clear_cache(doctype="Life Settings")

	def test_8_pins_are_per_user_and_stop_at_seven(self):
		people = [self.person(f"Pin {i} q111") for i in range(8)]
		for p in people[:7]:
			self.assertTrue(pages_api.pin("Life Person", p.name)["pinned"])
		refused = pages_api.pin("Life Person", people[7].name)
		self.assertTrue(refused["refused"])
		self.assertEqual(len(refused["choose_to_unpin"]), 7)
		frappe.set_user(FAMILY)
		self.assertEqual(pages_api.pinned()["pins"], [])
		frappe.set_user(OWNER)
		again = pages_api.pin("Life Person", people[7].name, replace=f"Life Person:{people[0].name}")
		self.assertEqual(len(again["pins"]), 7)
		self.assertEqual(again["pins"][-1]["name"], people[7].name)
		order = [f"Life Person:{p.name}" for p in reversed(people[1:])]
		self.assertEqual([p["name"] for p in pages_api.reorder(order)["pins"]], [p.name for p in reversed(people[1:])])

	def test_9_a_wrong_link_is_removed_kept_as_a_correction_and_not_made_again(self):
		org = self.person("Wrong q111", kind="Organisation")
		it = item("About something else q111", raw_text="x")
		subjects.link(PRIVATE, "Life Inbox Item", it, "Life Person", org.name)
		row = frappe.db.get_value("Life Link", {"to_name": org.name, "origin": "Brain"})
		pages_api.remove_link(row)
		self.assertEqual(subjects.timeline("Life Person", org.name)[1], 0)
		self.assertTrue(frappe.db.exists("Life Skill Correction", {"skill": "link-subjects", "correction_type": "Link"}))
		self.assertFalse(subjects.link(PRIVATE, "Life Inbox Item", it, "Life Person", org.name))

	def test_10_your_notes_are_kept_when_the_brief_is_rewritten(self):
		org = self.person("Notes q111", kind="Organisation")
		self.linked_item(org, "Email q111")
		pages_api.add_note("Life Person", org.name, "My own thought")
		self.script(say({"sentences": [{"text": "An email came.", "sources": [1]}]}))
		briefs.rewrite("Life Person", org.name, force=True)
		page = pages_api.get("Life Person", org.name)
		self.assertEqual([n["text"] for n in page["notes"]], ["My own thought"])
		self.assertEqual(page["brief"]["n_sources"], 1)
		frappe.set_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			pages_api.add_note("Life Person", org.name, "from an agent")
		frappe.set_user(OWNER)

	def test_11_ask_reads_a_page_first_and_cites_it(self):
		org = self.person("Read me q111", kind="Organisation")
		it = self.linked_item(org, "Quote email q111", raw_text="The quote is 4.2 lakh.")
		self.script(say({"sentences": [{"text": "A quote of 4.2 lakh came.", "sources": [1]}]}))
		briefs.rewrite("Life Person", org.name, force=True)
		from lifeos.ai import tools as ask_tools

		ctx = Context(PRIVATE)
		got = ask_tools.run_tool(ctx, "read_page", {"name": "Read me q111"})
		self.assertIn("4.2 lakh", got["brief"]["text"])
		self.assertEqual(got["timeline"][0]["title"], "Quote email q111")
		self.assertEqual(ctx.refs[got["page"]]["route"], f"/library/pages/Life Person/{org.name}")
		self.assertIn("error", ask_tools.run_tool(ctx, "read_page", {"name": "No such page q111"}))


class TestRelayedChat(LifeTestCase):
	"""Issue 125: the owner's conversation on an agent's channel, kept in one read-only thread in Chat."""
	KEY = "i125relay"

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.delete("Life Connection", {"space": PRIVATE, "system": self.KEY})
		frappe.db.delete("Life Agent Config", {"space": PRIVATE, "agent": self.KEY})
		for name in frappe.get_all("Life Ask Thread", filters={"space": ("in", [PRIVATE, SHARED]), "source_system": self.KEY}, pluck="name"):
			frappe.db.delete("Life Ask Message", {"thread": name})
			frappe.delete_doc("Life Ask Thread", name, force=True, ignore_permissions=True)
		self.connection = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": self.KEY, "label": "Hermes", "active": 1}).insert()
		self.cfg = frappe.get_doc({"doctype": "Life Agent Config", "space": PRIVATE, "agent": self.KEY, "display_name": "Hermes"}).insert()
		self.as_user(AGENT)

	TURNS = [{"role": "owner", "text": "Add a task to call Ekta", "at": "2026-11-26 09:00:00"}, {"role": "assistant", "text": "Done, it is on Today.", "at": "2026-11-26 09:00:05"},
		{"role": "owner", "text": "Thanks", "at": "2026-11-26 09:01:00"}]

	def relay(self, turns=None, external_id="tg-100"):
		return chats.relay(turns or self.TURNS, "Telegram", self.KEY, external_id, space=PRIVATE)

	# 5
	def test_5_three_turns_make_one_thread_a_repeat_adds_nothing_a_switched_off_source_is_refused_and_no_one_else_reads_it(self):
		from lifeos.api import ask

		out = self.relay()
		self.assertEqual(out["added"], 3)
		self.assertEqual(self.relay()["added"], 0)  # the same external_id again
		self.assertEqual(self.relay()["thread"], out["thread"])
		thread = frappe.get_doc("Life Ask Thread", out["thread"])
		self.assertEqual((thread.title, thread.channel, thread.user), ("Hermes · Telegram", "Telegram", OWNER))
		self.assertEqual(frappe.db.count("Life Ask Thread", {"space": PRIVATE, "source_system": self.KEY}), 1)
		self.as_user(OWNER)
		got = ask.thread(out["thread"])
		self.assertEqual([(m["role"], m["text"]) for m in got["messages"]], [("user", "Add a task to call Ekta"), ("assistant", "Done, it is on Today."), ("user", "Thanks")])
		self.assertEqual((got["readonly"], got["channel"], got["title"]), (1, "Telegram", "Hermes · Telegram"))
		listed = [t for t in ask.threads(space=PRIVATE, q="Telegram")["rows"] if t["name"] == out["thread"]]
		self.assertEqual((listed[0]["channel"], listed[0]["title"], listed[0]["questions"]), ("Telegram", "Hermes · Telegram", 2))
		with self.assertRaises(frappe.ValidationError):  # you reply on the channel, not here
			ask.ask("hello", space=PRIVATE, thread=out["thread"])
		self.as_user(AGENT)
		shared = chats.relay(self.TURNS, "Telegram", self.KEY, "tg-100", space=SHARED)  # the same talk in a space with a family member in it
		self.as_user(FAMILY)  # another member of the space
		with self.assertRaises(frappe.DoesNotExistError):
			ask.thread(shared["thread"])
		self.assertEqual([t for t in ask.threads(space=SHARED, q="Telegram")["rows"] if t["name"] == shared["thread"]], [])
		self.as_user(AGENT)  # an agent cannot read it back
		self.assertFalse(frappe.has_permission("Life Ask Thread", "read", doc=out["thread"], user=AGENT))
		self.assertFalse(frappe.has_permission("Life Ask Message", "read", doc=frappe.get_all("Life Ask Message", filters={"thread": out["thread"]}, limit=1)[0].name, user=AGENT))  # system: the test reads as the site
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Connection", self.connection.name, "active", 0)
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			self.relay([{"role": "owner", "text": "More", "at": "2026-11-26 10:00:00"}], "tg-200")
		self.as_user(OWNER)
		with self.assertRaises(frappe.PermissionError):  # only an agent relays
			self.relay()

	def test_a_turn_with_its_own_id_is_added_once_and_a_new_name_shows_in_the_title(self):
		from lifeos.api import ask

		self.relay([{"role": "owner", "text": "One", "id": "m1"}], "tg-1")
		self.assertEqual(self.relay([{"role": "owner", "text": "One", "id": "m1"}, {"role": "assistant", "text": "Two", "id": "m2"}], "tg-2")["added"], 1)
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Agent Config", self.cfg.name, "display_name", "Jai's assistant")
		self.as_user(OWNER)
		self.assertIn("Jai's assistant · Telegram", [t["title"] for t in ask.threads(space=PRIVATE, q="Telegram")["rows"]])
