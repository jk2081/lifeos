import frappe
from frappe.utils import add_days, getdate, today

from lifeos import archive, index
from lifeos.api import archive as archive_api
from lifeos.api import chats, library, links, timeline, vault
from lifeos.api import goals as goal_api
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


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
		from lifeos.devtools import attach
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
		self.goal = self.make("Life Goal", title="Mandir m7", goal_type="Open", area=self.areas["Tea"])

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
		page = self.make("Life Journal Page", page_date=add_days(today(), -900))
		person = self.make("Life Person", full_name="Old friend m7")
		date = self.make("Life Important Date", title="Old date m7", day=1, month=1)
		out = archive.run_daily()
		self.assertGreaterEqual(out["Life Task"], 2)

		def state(doc):
			return frappe.db.get_value(doc.doctype, doc.name, ["is_archived", "archive_reason"])

		for doc in (done_old, dropped_old, item_old, chat_quiet):
			self.assertEqual(state(doc), (1, "Auto"), doc.title)
			self.assertEqual(str(frappe.db.get_value(doc.doctype, doc.name, "archived_on")), today())
			self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": doc.name, "kind": ("!=", "Task Done")}, "is_archived"), 1)
		for doc in (done_new, stale_open, item_review, chat_open, vault_doc, note, page):
			self.assertEqual(state(doc)[0], 0, doc.get("title") or doc.doctype)
		for doc in (done_old, stale_open, vault_doc, note, person, date):
			self.assertTrue(frappe.db.exists(doc.doctype, doc.name))  # nothing is ever deleted
		# the stale open task is listed under Decide, and the week's archive shows with Undo
		from lifeos.api import journal
		review = journal.weekly_review(space=PRIVATE)
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
		goal = self.make("Life Goal", title="Finish me m7", goal_type="Open", area=self.areas["Tea"])
		task = self.make("Life Task", title="Goal task m7", area=self.areas["Tea"], goal=goal.name)
		note = self.make("Life Note", title="Goal note m7", area=self.areas["Tea"], goal=goal.name)
		chat = self.make("Life Chat Log", title="Goal chat m7", date=today(), area=self.areas["Tea"], goal=goal.name)
		outside = self.make("Life Task", title="Not under the goal m7", area=self.areas["Tea"])
		already = self.make("Life Note", title="Archived before m7", area=self.areas["Tea"], goal=goal.name, is_archived=1, archive_reason="Manual")
		self.assertEqual(goal_api.completion_info(goal.name)["records"], 3)
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
