import frappe
from frappe.utils import today

from lifeos.api import graph, inbox, search
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


def names(res):
	return [r["ref_name"] for r in res["results"]]


class TestSearch(LifeTestCase):
	def test_finds_a_word_in_a_transcript(self):
		item = inbox.create_item(title="Journal photo m8", source_type="Journal Photo", space=PRIVATE)
		self.as_user(AGENT)
		claimed = inbox.claim_next(space=PRIVATE)
		while claimed and claimed["name"] != item["name"]:
			inbox.submit_result(claimed["name"], summary_md="skip")
			claimed = inbox.claim_next(space=PRIVATE)
		inbox.submit_result(item["name"], transcript_md="Discuss going with Nowrojeezzz about the leased gardens", summary_md="s")
		frappe.db.commit()  # the full-text index sees committed rows only
		self.as_user(OWNER)
		res = search.query("nowrojeezzz", space=PRIVATE)
		self.assertEqual(names(res), [item["name"]])
		self.assertEqual(res["results"][0]["kind"], "Inbox")
		self.assertIn("Nowrojeezzz", res["results"][0]["snippet"])
		self.assertEqual(res["results"][0]["route"], f"/inbox/{item['name']}")
		self.assertEqual(names(search.query("nowrojeez", space=PRIVATE)), [item["name"]])  # prefix

	def test_searches_every_filed_type(self):
		made = {
			"note": self.make("Life Note", title="Quartzite note m8", content_md="about zebrafish"),
			"task": self.make("Life Task", title="Quartzite task m8"),
			"chat": self.make("Life Chat Log", title="Quartzite chat m8", date=today(), summary_md="s"),
			"vault": self.make("Life Vault Document", title="Quartzite passport m8"),
			"page": self.make("Life Journal Page", page_date=today(), transcript_md="quartzite on the page"),
		}
		frappe.db.commit()
		got = names(search.query("quartzite"))
		for doc in made.values():
			self.assertIn(doc.name, got)
		self.assertEqual(names(search.query("zebrafish")), [made["note"].name])
		self.assertEqual(names(search.query("quartzite zebrafish")), [made["note"].name])  # every word must match
		self.assertEqual(names(search.query("m8 xyznotthere")), [])
		self.assertEqual(search.query("   ")["results"], [])
		self.assertLessEqual(len(search.query("quartzite", limit=2)["results"]), 2)

	def test_outsider_finds_nothing_from_a_private_space(self):
		secret = self.make("Life Note", title="Obsidianite secret m8", content_md="obsidianite plans")
		shared = self.make("Life Note", space=SHARED, title="Obsidianite shopping m8")
		frappe.db.commit()
		self.assertEqual(sorted(names(search.query("obsidianite"))), sorted([secret.name, shared.name]))
		self.as_user(FAMILY)
		self.assertEqual(names(search.query("obsidianite")), [shared.name])
		self.assertRaises(frappe.PermissionError, search.query, "obsidianite", space=PRIVATE)
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, search.query, "obsidianite")

	def test_archived_records_are_hidden_unless_asked(self):
		note = self.make("Life Note", title="Feldsparite archived m8", is_archived=1)
		frappe.db.commit()
		self.assertEqual(names(search.query("feldsparite")), [])
		self.assertEqual(names(search.query("feldsparite", include_archived=1)), [note.name])

	def test_short_and_odd_words_fall_back(self):
		note = self.make("Life Note", title="ZQ m8 pan", content_md="x")
		frappe.db.commit()
		self.assertIn(note.name, names(search.query("zq")))
		self.assertEqual(search.query("+-*()\"")["results"], [])


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
