"""UX fixes, set 3: the counts on the state tabs of the list screens.
Each list method returns `tabs`, the number of records on every tab under the other filters. The checks below hold each
count against the list that tab asks for, with and without another filter, and for a member of another space."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos import permissions
from lifeos.api import archive, area, chats, inbox, library, projects, tasks, timeline, vault
from lifeos.api import today as today_api
from lifeos.tests.base import FAMILY, PRIVATE, SHARED, LifeTestCase


class TestTabCounts(LifeTestCase):
	def test_tasks(self):
		tea, money = self.areas["Tea"], self.areas["Money"]
		self.make("Life Task", title="ux3t open", area=tea)
		self.make("Life Task", title="ux3t doing", area=tea, status="Doing")
		self.make("Life Task", title="ux3t waiting", area=tea, status="Waiting", waiting_on="the bank", due_date=today())
		self.make("Life Task", title="ux3t done", area=money, status="Done")
		self.make("Life Task", title="ux3t dropped", area=money, status="Dropped")
		old = self.make("Life Task", title="ux3t loop", area=money, status="Waiting", waiting_on="a reply")
		frappe.db.set_value("Life Task", old.name, "creation", add_days(today(), -30), update_modified=False)

		def check(**f):
			get = lambda **a: tasks.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(set(tabs), {"open", "loops", "Waiting", "Done", "all"})
			self.assertEqual(tabs["open"], get(status="open_doing")["total"])
			self.assertEqual(tabs["loops"], get(status="open", loops=1)["total"])
			self.assertEqual(tabs["Waiting"], get(status="Waiting")["total"])
			self.assertEqual(tabs["Done"], get(status="Done")["total"])
			self.assertEqual(tabs["all"], get(status="all")["total"])
			# the counts do not depend on the tab that is asked for
			self.assertEqual(get(status="Done")["tabs"], tabs)
			self.assertEqual(get(status="open", loops=1)["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3t %"]]  # other tests of this class leave tasks in the space
		check()
		tabs = check(filters=mine)
		self.assertEqual((tabs["open"], tabs["loops"], tabs["Waiting"], tabs["Done"], tabs["all"]), (2, 1, 2, 1, 6))
		in_tea = check(area=tea, filters=mine)
		self.assertEqual((in_tea["open"], in_tea["loops"], in_tea["Waiting"], in_tea["Done"], in_tea["all"]), (2, 0, 1, 0, 3))
		check(due="today,overdue")
		self.assertEqual(check(filters=[["title", "like", "ux3t d"]])["all"], 3)
		# "open" in the API still holds Waiting tasks; the Open tab and every number that leads to it do not
		self.assertEqual(tasks.list(space=PRIVATE, filters=mine)["total"], 4)
		self.assertEqual(tasks.count(PRIVATE, area=tea), tasks.list(space=PRIVATE, area=tea)["tabs"]["open"])
		self.assertEqual(today_api.get(space=PRIVATE)["tasks"]["due"], tasks.list(space=PRIVATE, status="open_doing", due="today,overdue")["total"])

	def test_inbox(self):
		tea = self.areas["Tea"]
		for i, status in enumerate(["New", "Processing", "To Review", "To Review", "Failed", "Done"]):
			doc = self.make("Life Inbox Item", title=f"ux3 inbox {i}", source_type="Message", raw_text="x", area=tea if i % 2 else None)
			frappe.db.set_value("Life Inbox Item", doc.name, "status", status)

		def check(**f):
			get = lambda **a: inbox.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(tabs["To Review"], get(status="To Review")["total"])
			self.assertEqual(tabs["Waiting"], get(status='["New", "Processing"]')["total"])
			self.assertEqual(tabs["Failed"], get(status="Failed")["total"])
			self.assertEqual(tabs["Done"], get(status="Done")["total"])
			self.assertEqual(tabs["all"], get()["total"])
			self.assertEqual(get(status="Done")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 inbox %"]]
		check()
		self.assertEqual(check(filters=mine), {"To Review": 2, "Waiting": 2, "Failed": 1, "Done": 1, "all": 6})
		self.assertEqual(check(area=tea, filters=mine), {"To Review": 1, "Waiting": 1, "Failed": 0, "Done": 1, "all": 3})
		check(source_type="Message")

	def test_projects(self):
		tea, money = self.areas["Tea"], self.areas["Money"]
		self.make("Life Project", title="ux3 p active", area=tea)
		self.make("Life Project", title="ux3 p active 2", area=money)
		self.make("Life Project", title="ux3 p hold", area=tea, status="On Hold")
		self.make("Life Project", title="ux3 p dropped", area=money, status="Dropped")
		done = self.make("Life Project", title="ux3 p done", area=tea)
		projects.set_status(done.name, "Done")

		def check(**f):
			get = lambda **a: projects.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			for status in ("Active", "On Hold", "Done", "Dropped"):
				self.assertEqual(tabs[status], get(status=status)["total"], status)
			self.assertEqual(tabs["all"], get(include_done=1)["total"])
			self.assertEqual(tabs["current"], get()["total"])  # active and on hold: the area page's Projects tab
			self.assertEqual(get(status="Done")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 p %"]]
		check()
		self.assertEqual(check(filters=mine), {"current": 3, "Active": 2, "On Hold": 1, "Done": 1, "Dropped": 1, "all": 5})
		self.assertEqual(check(area=tea, filters=mine), {"current": 2, "Active": 1, "On Hold": 1, "Done": 1, "Dropped": 0, "all": 3})

	def test_archive(self):
		tea = self.areas["Tea"]
		task = self.make("Life Task", title="ux3 archived task", area=tea, status="Done")
		note = self.make("Life Note", title="ux3 archived note", area=tea, body_md="x")
		other = self.make("Life Note", title="ux3 archived note 2", area=self.areas["Money"], body_md="x")
		for doc in (task, note, other):
			archive.set(doc.doctype, doc.name)

		def check(**f):
			get = lambda **a: archive.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(set(tabs), {"all", "Life Task", "Life Note", "Life Inbox Item", "Life Chat Log", "Life Vault Document", "Life Journal Page"})
			for dt in tabs:
				self.assertEqual(tabs[dt], get(doctype=None if dt == "all" else dt)["total"], dt)
			self.assertEqual(get(doctype="Life Note")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 archived %"]]
		check()
		tabs = check(filters=mine)
		self.assertEqual((tabs["all"], tabs["Life Task"], tabs["Life Note"], tabs["Life Chat Log"]), (3, 1, 2, 0))
		in_tea = check(area=tea, filters=mine)
		self.assertEqual((in_tea["all"], in_tea["Life Task"], in_tea["Life Note"]), (2, 1, 1))
		check(reason="Manual")

	def test_chats(self):
		tea = self.areas["Tea"]
		chats.log(space=PRIVATE, title="ux3 chat open", summary_md="s", open_items=["call the bank"], area=tea)
		chats.log(space=PRIVATE, title="ux3 chat quiet", summary_md="s", area=tea)
		chats.log(space=PRIVATE, title="ux3 chat open 2", summary_md="s", open_items=["write back"])

		def check(**f):
			get = lambda **a: chats.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(tabs["all"], get()["total"])
			self.assertEqual(tabs["open"], get(open_items=1)["total"])
			self.assertEqual(get(open_items=1)["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 chat %"]]
		check()
		self.assertEqual(check(filters=mine), {"all": 3, "open": 2})
		self.assertEqual(check(area=tea, filters=mine), {"all": 2, "open": 1})

	def test_vault(self):
		now = getdate(today())
		tea = self.areas["Tea"]
		self.make("Life Vault Document", title="ux3 expired", doc_type="Travel", area=tea, expiry_date=add_days(now, -5))
		self.make("Life Vault Document", title="ux3 soon", doc_type="Travel", area=tea, expiry_date=add_days(now, 30))
		self.make("Life Vault Document", title="ux3 soon 2", doc_type="Insurance", area=self.areas["Money"], expiry_date=add_days(now, 60))
		self.make("Life Vault Document", title="ux3 later", doc_type="Insurance", area=tea, expiry_date=add_days(now, 61))
		self.make("Life Vault Document", title="ux3 no date", doc_type="Other", area=tea)

		def check(**f):
			get = lambda **a: vault.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(tabs["all"], get()["total"])
			self.assertEqual(tabs["soon"], get(expiry="soon")["total"])
			self.assertEqual(tabs["expired"], get(expiry="expired")["total"])
			self.assertEqual(get(expiry="expired")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 %"], ["title", "not like", "ux3 private%"]]
		self.assertEqual(check(filters=mine), {"all": 5, "soon": 2, "expired": 1})
		self.assertEqual(check(area=tea, filters=mine), {"all": 4, "soon": 1, "expired": 1})
		self.assertEqual(check(doc_type="Insurance", filters=mine), {"all": 2, "soon": 1, "expired": 0})
		# the Expiring soon tab is the 60-day window Today counts
		self.assertEqual(check()["soon"], today_api.get(space=PRIVATE)["vault_soon"])

	def test_a_member_of_another_space_sees_only_their_own_counts(self):
		self.make("Life Task", title="ux3 private task")
		self.make("Life Task", title="ux3 shared task", space=SHARED)
		self.make("Life Project", title="ux3 private project", area=self.areas["Tea"])
		self.make("Life Vault Document", title="ux3 private doc", doc_type="Travel", area=self.areas["Tea"], expiry_date=add_days(today(), 10))
		chats.log(space=PRIVATE, title="ux3 private chat", summary_md="s", open_items=["x"])
		self.make("Life Inbox Item", title="ux3 private inbox", source_type="Message", raw_text="x")
		note = self.make("Life Note", title="ux3 private archived", body_md="x")
		archive.set("Life Note", note.name)
		owner_tabs = tasks.list(space=SHARED)["tabs"]
		self.assertEqual(owner_tabs["open"], 1)
		self.assertGreaterEqual(tasks.list(space=PRIVATE)["tabs"]["open"], 1)

		self.as_user(FAMILY)
		# the family member is in the shared space only: its counts are the shared space's, and the private space is refused
		self.assertEqual(tasks.list(space=SHARED)["tabs"], owner_tabs)
		for method in (tasks.list, inbox.list, projects.list, archive.list, chats.list, vault.list):
			self.assertRaises(frappe.PermissionError, method, space=PRIVATE)
			tabs = method(space=SHARED)["tabs"]
			self.assertEqual(sum(tabs.values()), 2 if method is tasks.list else 0, method.__module__)
		self.assertNotIn(PRIVATE, permissions.user_spaces())


class TestRecordPageTabs(LifeTestCase):
	"""The tab counts of the area and project pages equal the main screen's list filtered by that area or project."""

	def test_area_page(self):
		tea = self.areas["Tea"]
		p = self.make("Life Project", title="ux3 area project", area=tea)
		self.make("Life Task", title="ux3 area task", area=tea)
		self.make("Life Task", title="ux3 area waiting", area=tea, status="Waiting", waiting_on="x")
		self.make("Life Note", title="ux3 area note", area=tea, project=p.name)
		self.make("Life Vault Document", title="ux3 area doc", doc_type="Other", area=tea)
		chats.log(space=PRIVATE, title="ux3 area chat", summary_md="s", area=tea)
		self.make("Life Note", title="ux3 area wiki page", area=tea, collection="Wiki", summary="A page")  # set 4: the Wiki tab
		tabs = area.get(tea)["tabs"]
		self.assertEqual(tabs["projects"], projects.list(space=PRIVATE, area=tea)["total"])
		self.assertEqual(tabs["tasks"], tasks.list(space=PRIVATE, area=tea, status="open_doing")["total"])
		self.assertEqual(tabs["notes"], library.list(space=PRIVATE, area=tea)["total"])
		self.assertEqual(tabs["wiki"], library.list(space=PRIVATE, area=tea, collection="Wiki")["total"])
		self.assertEqual(tabs["documents"], vault.list(space=PRIVATE, area=tea)["total"])
		self.assertEqual(tabs["chats"], chats.list(space=PRIVATE, area=tea)["total"])
		self.assertEqual(tabs["timeline"], timeline.get(space=PRIVATE, area=tea)["total"])
		self.assertTrue(all(tabs[k] >= 1 for k in tabs))

	def test_project_page(self):
		tea = self.areas["Tea"]
		p = self.make("Life Project", title="ux3 page project", area=tea)
		self.make("Life Task", title="ux3 page task", area=tea, project=p.name)
		self.make("Life Task", title="ux3 page done", area=tea, project=p.name, status="Done")
		self.make("Life Note", title="ux3 page note", area=tea, project=p.name, content_md="see [[ux3 page project]]")
		tabs = projects.get(p.name)["tabs"]
		self.assertEqual(tabs["tasks"], 1)
		self.assertEqual(tabs["notes"], 1)
		self.assertEqual(tabs["documents"], 0)
		self.assertEqual(tabs["chats"], 0)
		self.assertGreaterEqual(tabs["links"], 1)

	def test_other_space_member_cannot_read_the_counts(self):
		tea = self.areas["Tea"]
		p = self.make("Life Project", title="ux3 hidden project", area=tea)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, area.get, tea)
		self.assertRaises(frappe.PermissionError, projects.get, p.name)
