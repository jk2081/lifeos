"""Load test at the size in section 4b of the spec: 100,000 index rows, 20 users, 50 spaces.

	bench --site SITE execute lifeos.loadtest.run       seed, measure, remove; prints the timings
	bench --site SITE execute lifeos.loadtest.seed      only seed (spaces named "Load 01" to "Load 50")
	bench --site SITE execute lifeos.loadtest.measure   only measure
	bench --site SITE execute lifeos.loadtest.remove    remove everything the seed made

Rows are written with bulk SQL, not through the document API, so seeding takes about a minute.
Two fifths of the rows are real `Life Task` records with their index rows; the rest are index rows of the
other kinds (notes, chats, inbox items, documents). Half of all rows sit in one space, "Load 01",
which is the space the timings are taken in. For a test site only.
"""
import random
import statistics
import time

import frappe
from frappe.utils import add_days, getdate, now, today

from lifeos import devtools, index, permissions, seed as seed_data

PREFIX = "Load "
TARGET_MS = 500
AREAS = ["Work", "Personal & Health", "Money & Legal", "Family", "Learning", "Estates", "Projects", "Travel"]
KINDS = [("Life Note", "Note"), ("Life Chat Log", "Chat"), ("Life Inbox Item", "Inbox"), ("Life Vault Document", "Document")]
SYLLABLES = ["ka", "ri", "mo", "te", "sun", "dar", "vel", "pho", "gan", "lit", "ost", "rem", "bui", "cha", "nes", "tor", "ula", "pin", "zed", "wom"]
RARE_WORD = "quillonberry"


def _vocabulary(rng, size=3000):
	words = set()
	while len(words) < size:
		words.add("".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 4))))
	return sorted(words)


def space_names(spaces=50):
	return [f"{PREFIX}{i:02d}" for i in range(1, spaces + 1)]


def seed(rows=100000, users=20, spaces=50, big_share=0.5):
	"""Create the spaces, users and rows. Safe to run again: it removes an earlier load first."""
	remove()
	frappe.set_user("Administrator")
	rng = random.Random(7)
	vocab = _vocabulary(rng)
	rows, users, spaces = int(rows), int(users), int(spaces)
	emails = [devtools.OWNER] + [f"load{i:02d}@lifeos.test" for i in range(1, users)]
	for i, email in enumerate(emails):
		devtools.make_user(email, "Jai" if i == 0 else f"Load {i:02d}", ["Life Admin", "Life User"] if i == 0 else ["Life User"])
	names = space_names(spaces)
	areas = {}
	for i, name in enumerate(names):
		# every user is in the big space and in a few of the others
		members = emails if i == 0 else sorted({emails[0], emails[i % len(emails)], emails[(i * 7) % len(emails)]})
		frappe.get_doc({"doctype": "Life Space", "space_name": name, "owner_user": emails[0],
			"members": [{"user": u, "access": "Write"} for u in members]}).insert(ignore_permissions=True)
		areas[name] = list(seed_data.make_areas(name, AREAS).values())
	permissions.clear_cache()

	ts, day0 = now(), getdate(today())
	task_cols = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "space", "title", "status", "priority",
		"due_date", "area", "is_archived", "last_touched_on", "completed_on"]
	index_cols = index.COLUMNS
	# the columns set 4 added to the index, after the 21 these rows spell out
	pad = tuple(0 if c == "vault_locked" else None if c in index.NULLABLE else "" for c in index.COLUMNS[21:])
	tasks, idx = [], []

	def flush(force=False):
		nonlocal tasks, idx
		if tasks and (force or len(tasks) >= 2000):
			frappe.db.bulk_insert("Life Task", task_cols, tasks)
			tasks = []
		if idx and (force or len(idx) >= 2000):
			frappe.db.bulk_insert("Life Index", index_cols, idx)
			idx = []

	big = int(rows * big_share)
	per_other = (rows - big) // max(spaces - 1, 1)
	made = 0
	for si, space in enumerate(names):
		count = big if si == 0 else per_other
		for n in range(count):
			made += 1
			owner = emails[rng.randrange(len(emails))]
			area = rng.choice(areas[space])
			age = int(rng.random() ** 2 * 1500)  # most records are recent, some are four years old
			day = add_days(day0, -age)
			created = f"{day} 10:00:00"
			title = " ".join(rng.choice(vocab) for _ in range(rng.randint(3, 7))).capitalize()
			text = " ".join(rng.choice(vocab) for _ in range(rng.randint(30, 120)))
			if made % 4000 == 0:
				text += " " + RARE_WORD
			also = f",{rng.choice(areas[space])}," if rng.random() < 0.05 else ""
			if n % 5 < 2:
				# a real task: nine in ten are done and archived, as they would be after some years
				name = f"load-t-{made:07d}"
				done = rng.random() < 0.9
				status = "Done" if done else rng.choice(["Open", "Open", "Doing", "Waiting"])
				due = None if rng.random() < 0.5 else add_days(day, rng.randint(0, 30))
				archived = 1 if done and age > 90 else 0
				tasks.append((name, created, created, owner, owner, 0, 0, space, title, status, rng.choice(["I", "II", "III", "IV", ""]),
					due, area, archived, day, add_days(day, 3) if done else None))
				idx.append((index.row_name("Life Task", name, "Task"), created, created, owner, owner, 0, 0, "Life Task", name, space,
					area, also, "", "", day, title, text, archived, "Task", status, owner) + pad)
			else:
				doctype, kind = KINDS[n % len(KINDS)]
				name = f"load-x-{made:07d}"
				archived = 1 if kind in ("Chat", "Inbox") and age > 90 else 0
				idx.append((index.row_name(doctype, name, kind), created, created, owner, owner, 0, 0, doctype, name, space,
					area, also, "", "", day, title, text, archived, kind, "", owner) + pad)
			flush()
	flush(force=True)
	frappe.db.commit()
	return {"rows": frappe.db.count("Life Index", {"space": ("like", PREFIX + "%")}), "users": len(emails), "spaces": len(names)}


def _time(fn, runs=5):
	fn()  # warm the caches once, as a second page view would find them
	times = []
	for _ in range(runs):
		frappe.local.request_cache.clear() if hasattr(frappe.local, "request_cache") else None
		start = time.perf_counter()
		fn()
		times.append((time.perf_counter() - start) * 1000)
	return {"median_ms": round(statistics.median(times), 1), "max_ms": round(max(times), 1)}


def measure(user=None, space=None):
	"""Time the four reads the spec names, as a member of the largest space."""
	from lifeos.api import area as area_api
	from lifeos.api import search, timeline
	from lifeos.api import today as today_api

	space = space or space_names(1)[0]
	before = frappe.session.user
	frappe.set_user(user or devtools.OWNER)
	permissions.clear_cache()
	try:
		area = frappe.db.get_value("Life Area", {"space": space}, "name", order_by="sort_order asc, creation asc")
		word = frappe.db.sql("select title from `tabLife Index` where space=%s limit 1 offset 500", space)[0][0].split()[0].lower()
		out = {
			"index_rows": frappe.db.count("Life Index"),
			"rows_in_space": frappe.db.count("Life Index", {"space": space}),
			"today": _time(lambda: today_api.get(space=space)),
			"timeline": _time(lambda: timeline.get(space=space)),
			"timeline_page_20": _time(lambda: timeline.get(space=space, start=1000, page_length=50)),
			"area_page": _time(lambda: area_api.get(area)),
			"search_common_word": _time(lambda: search.query(word, space=space)),
			"search_rare_word": _time(lambda: search.query(RARE_WORD, space=space)),
			"search_all_spaces": _time(lambda: search.query(word)),
			"search_two_words": _time(lambda: search.query(word + " " + RARE_WORD[:5], space=space)),
		}
	finally:
		frappe.set_user(before)
	out["target_ms"] = TARGET_MS
	out["slowest_ms"] = max(v["median_ms"] for v in out.values() if isinstance(v, dict))
	out["passed"] = out["slowest_ms"] < TARGET_MS
	return out


# ---------- UX fixes, set 4: sources and the wiki at scale ----------
SOURCE_KINDS = [("Voice", "Voice Note"), ("Document", "Upload"), ("Photo", "Upload"), ("Article", "Web"), ("Email", "Email"),
	("Email Digest", "Email Digest"), ("Text", "Message")]


def seed_sources(sources=20000, pages=2000, space=None, text_chars=5000):
	"""Add `sources` sources (nine in ten inbox items, one in ten chat logs) with about `text_chars` characters of text each, and
	`pages` wiki pages with two changes each, to the big load space. Bulk SQL, like seed(). Run seed() first."""
	frappe.set_user("Administrator")
	rng = random.Random(11)
	vocab = _vocabulary(rng)
	space = space or space_names(1)[0]
	areas = frappe.get_all("Life Area", filters={"space": space}, pluck="name") or [""]
	owner = devtools.OWNER
	ts, day0 = now(), getdate(today())
	pad = {c: (0 if c == "vault_locked" else None if c in index.NULLABLE else "") for c in index.COLUMNS[21:]}

	def words(n):
		out, size = [], 0
		while size < n:
			w = rng.choice(vocab)
			out.append(w)
			size += len(w) + 1
		return " ".join(out)

	item_cols = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "space", "title", "source_type", "received_on",
		"transcript_md", "summary_md", "status", "intent", "media_kind", "area", "is_archived", "source_system", "thumbnail"]
	chat_cols = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "space", "title", "date", "assistant",
		"transcript_md", "area", "is_archived", "source_system", "external_id"]
	items, chats, idx = [], [], []

	def index_row(dt, name, kind, created, day, area, title, text, status, extra):
		row = {**pad, **extra}
		return (index.row_name(dt, name, kind), created, created, owner, owner, 0, 0, dt, name, space, area, "", "", "", day, title, text[:index.SEARCH_CAP],
			0, kind, status, owner) + tuple(row[c] for c in index.COLUMNS[21:])

	def flush(force=False):
		nonlocal items, chats, idx
		if items and (force or len(items) >= 500):
			frappe.db.bulk_insert("Life Inbox Item", item_cols, items)
			items = []
		if chats and (force or len(chats) >= 500):
			frappe.db.bulk_insert("Life Chat Log", chat_cols, chats)
			chats = []
		if idx and (force or len(idx) >= 500):
			frappe.db.bulk_insert("Life Index", index.COLUMNS, idx)
			idx = []

	for n in range(int(sources)):
		age = int(rng.random() ** 2 * 1500)
		day = add_days(day0, -age)
		created = f"{day} 09:00:00"
		area = rng.choice(areas)
		title = " ".join(rng.choice(vocab) for _ in range(rng.randint(3, 7))).capitalize()
		text = words(text_chars) + (" " + RARE_WORD if n % 2000 == 0 else "")
		if n % 10 == 9:
			name = f"load-c-{n:07d}"
			chats.append((name, created, created, owner, owner, 0, 0, space, title, day, rng.choice(["Claude", "ChatGPT"]), text, area, 0, "claude", name))
			idx.append(index_row("Life Chat Log", name, "Chat", created, day, area, title, text, "", {"media_kind": "Chat", "source_system": "claude", "assistant": "Claude"}))
		else:
			kind, stype = SOURCE_KINDS[n % len(SOURCE_KINDS)]
			name = f"load-s-{n:07d}"
			status = "Done" if rng.random() < 0.9 else "To Review"
			thumb = f"/private/files/{name}-thumb.jpg" if kind == "Photo" else ""
			items.append((name, created, created, owner, owner, 0, 0, space, title, stype, created, text, words(300), status, "Process", kind, area, 0,
				"gmail" if kind.startswith("Email") else "upload", thumb))
			idx.append(index_row("Life Inbox Item", name, "Inbox", created, day, area, title, text, status,
				{"media_kind": kind, "source_system": "gmail" if kind.startswith("Email") else "upload", "intent": "Process", "thumbnail": thumb}))
		flush()
	flush(force=True)

	note_cols = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "space", "title", "content_md", "collection", "summary",
		"area", "is_archived", "is_rules"]
	change_cols = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "space", "note", "change_type", "changed_by", "changed_on",
		"change_note", "before_md", "after_md", "reverted"]
	notes, changes = [], []
	for n in range(int(pages)):
		name = f"load-w-{n:06d}"
		day = add_days(day0, -int(rng.random() * 400))
		created = f"{day} 11:00:00"
		title = " ".join(rng.choice(vocab) for _ in range(rng.randint(2, 4))).title() + f" {n}"
		body = words(2000) + " [[" + " ".join(rng.choice(vocab) for _ in range(2)).title() + "]]"
		area = rng.choice(areas)
		notes.append((name, created, created, owner, owner, 0, 0, space, title, body, "Wiki", "One line about " + title, area, 0, 0))
		idx.append(index_row("Life Note", name, "Note", created, day, area, title, body, "", {"collection": "Wiki"}))
		for k, (ctype, before, after) in enumerate((("Created", "", body[:1000]), ("Edited", body[:1000], body))):
			changes.append((f"load-wc-{n:06d}-{k}", created, created, AGENT_USER, AGENT_USER, 0, 0, space, name, ctype, AGENT_USER,
				f"{day} 11:0{k}:00", "Load test change", before, after, 0))
		if len(notes) >= 500:
			frappe.db.bulk_insert("Life Note", note_cols, notes)
			frappe.db.bulk_insert("Life Wiki Change", change_cols, changes)
			notes, changes = [], []
		flush()
	if notes:
		frappe.db.bulk_insert("Life Note", note_cols, notes)
		frappe.db.bulk_insert("Life Wiki Change", change_cols, changes)
	flush(force=True)
	frappe.db.commit()
	return {"sources": frappe.db.count("Life Index", {"space": space, "kind": ("in", ["Inbox", "Chat"])}),
		"wiki_pages": frappe.db.count("Life Note", {"space": space, "collection": "Wiki"})}


AGENT_USER = "hermes@lifeos.test"


def measure_sources(user=None, space=None):
	"""Time the reads of the Sources and Wiki screens in the big load space: the Sources first page, a tab switch, a full-text
	search (the app's search and the wiki's), the Wiki Pages list and the Changes list."""
	from lifeos.api import search, sources, wiki

	space = space or space_names(1)[0]
	before = frappe.session.user
	frappe.set_user(user or devtools.OWNER)
	permissions.clear_cache()
	try:
		word = frappe.db.sql("select title from `tabLife Index` where space=%s and kind='Inbox' limit 1 offset 700", space)[0][0].split()[0].lower()
		out = {
			"sources": frappe.db.count("Life Index", {"space": space, "kind": ("in", ["Inbox", "Chat"])}),
			"wiki_pages": frappe.db.count("Life Note", {"space": space, "collection": "Wiki"}),
			"sources_first_page": _time(lambda: sources.list(space=space)),
			"sources_tab_photos": _time(lambda: sources.list(space=space, tab="photos")),
			"sources_tab_chats": _time(lambda: sources.list(space=space, tab="chats")),
			"search_full_text": _time(lambda: search.query(word, space=space)),
			"search_rare_word": _time(lambda: search.query(RARE_WORD, space=space)),
			"wiki_search": _time(lambda: wiki.search(space, word, include_sources=1)),
			"wiki_pages_list": _time(lambda: wiki.pages(space=space)),
			"wiki_changes_list": _time(lambda: wiki.changes(space=space)),
		}
	finally:
		frappe.set_user(before)
	out["target_ms"] = TARGET_MS
	out["slowest_ms"] = max(v["median_ms"] for v in out.values() if isinstance(v, dict))
	out["passed"] = out["slowest_ms"] < TARGET_MS
	return out


def run_sources(rows=100000, sources=20000, pages=2000, keep=0):
	"""The set 4 scale check: the milestone 9 load, plus sources and wiki pages, then the timings of both."""
	out = {"seeded": seed(rows), "sources": seed_sources(sources, pages)}
	try:
		out["timings"] = measure()
		out["timings_sources"] = measure_sources()
	finally:
		if not int(keep or 0):
			remove()
	return out


def remove():
	"""Remove the load spaces, their rows and the load users."""
	frappe.set_user("Administrator")
	for name in frappe.get_all("Life Space", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
		devtools.purge_space(name, drop=True)
	for email in frappe.get_all("User", filters={"name": ("like", "load%@lifeos.test")}, pluck="name"):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	permissions.clear_cache()
	frappe.db.commit()
	return "Load data removed."


def run(rows=100000, users=20, spaces=50, keep=0):
	out = {"seeded": seed(rows, users, spaces)}
	try:
		out["timings"] = measure()
	finally:
		if not int(keep or 0):
			remove()
	return out
