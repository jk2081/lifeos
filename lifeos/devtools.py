"""Helpers for the local test site and the test suite. Not used in production."""
import frappe

OWNER, FAMILY, AGENT = "owner@lifeos.test", "family@lifeos.test", "hermes@lifeos.test"


def make_user(email, first_name, roles, password=None):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0,
			"user_type": "System User"}).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
	missing = [r for r in roles if r not in [x.role for x in user.roles]]
	if missing:
		user.flags.ignore_permissions = True
		user.add_roles(*missing)
	if password:
		from frappe.utils.password import update_password
		update_password(email, password)
	return user


def setup_users(password=None):
	"""Create the three test users: the owner, a family member who is only in Shared, and an agent.

	Run: bench --site SITE execute lifeos.devtools.setup_users --kwargs "{'password': '...'}"
	"""
	from lifeos import install, permissions

	make_user(OWNER, "Jai", ["Life Admin", "Life User"], password)
	make_user(FAMILY, "Family", ["Life User"], password)
	make_user(AGENT, "Hermes", ["Life Agent"], password)
	install.set_owner(OWNER)
	install.add_member("Shared", FAMILY, "Write", "Life User")
	install.add_member("Private", AGENT, "Write", "Life Agent")
	install.add_member("Shared", AGENT, "Write", "Life Agent")
	permissions.clear_cache()
	return "Users ready."


def agent_api_key(user=AGENT):
	"""Create an API key and secret for an agent user and print them once. Never stored in the repo."""
	doc = frappe.get_doc("User", user)
	secret = frappe.generate_hash(length=15)
	if not doc.api_key:
		doc.api_key = frappe.generate_hash(length=15)
	doc.api_secret = secret
	doc.save(ignore_permissions=True)
	return f"{doc.api_key}:{secret}"


def purge_space(space, drop=False):
	"""Delete every lifeos record in a space with plain SQL. For test spaces only."""
	from lifeos.constants import SPACE_DOCTYPES

	for dt in SPACE_DOCTYPES:
		meta = frappe.get_meta(dt)
		# their files too, so a test leaves no file behind (UX fixes, set 4)
		# nosemgrep: frappe-sql-format-injection -- development tool: dt comes from the SPACE_DOCTYPES constant; values are parameters
		for f in frappe.db.sql(f"""select f.name, f.file_url, f.is_private from tabFile f join `tab{dt}` r on r.name = f.attached_to_name
				where f.attached_to_doctype = %s and r.space = %s""", (dt, space), as_dict=True):
			_delete_file(f)
		for tf in meta.get_table_fields():
			# nosemgrep: frappe-sql-format-injection -- development tool: table names from SPACE_DOCTYPES and their meta's table fields; values are parameters
			frappe.db.sql(
				f"delete c from `tab{tf.options}` c join `tab{dt}` p on p.name = c.parent where c.parenttype=%s and p.space=%s", (dt, space))
		# nosemgrep: frappe-sql-format-injection -- development tool: dt comes from the SPACE_DOCTYPES constant; space is a parameter
		frappe.db.sql(f"delete from `tab{dt}` where space=%s", space)
	frappe.db.sql("delete from `tabEvent` where life_space=%s", space)
	if drop:
		frappe.db.sql("delete from `tabLife Space Member` where parent=%s", space)
		frappe.db.sql("delete from `tabLife Space` where name=%s", space)


def _delete_file(f):
	"""Remove a File row, and the stored file when no other row points at it."""
	import os

	frappe.db.sql("delete from tabFile where name=%s", f.name)
	if f.file_url and not frappe.db.exists("File", {"file_url": f.file_url}):
		path = frappe.get_site_path("private" if f.is_private else "public", "files", os.path.basename(f.file_url))
		if os.path.exists(path):
			os.remove(path)


def load_fake_agent():
	"""Import agent/fake_agent.py from the repo."""
	import importlib.util
	import os

	path = os.path.join(frappe.get_app_path("lifeos"), "..", "agent", "fake_agent.py")
	spec = importlib.util.spec_from_file_location("fake_agent", path)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


class LocalClient:
	"""Runs the fake agent against the API methods in-process, as the session user."""

	def call(self, method, **args):
		module, fn = method.split(".")
		return frappe.get_attr(f"lifeos.api.{module}.{fn}")(**args)

	def download(self, file_url):
		doc = frappe.get_doc("File", {"file_url": file_url})
		doc.check_permission("read")
		return doc.get_content()


def attach(doctype, name, file_name, content=b"hello", fieldname=None):
	return frappe.get_doc({"doctype": "File", "file_name": file_name, "attached_to_doctype": doctype, "attached_to_name": name,
		"attached_to_field": fieldname, "is_private": 1, "content": content}).insert()


def pdf_bytes():
	import io

	from pypdf import PdfWriter

	writer, buf = PdfWriter(), io.BytesIO()
	writer.add_blank_page(width=595, height=842)
	writer.write(buf)
	return buf.getvalue()


def journal_png(lines=None):
	"""A stand-in for a photographed journal page."""
	import io

	from PIL import Image, ImageDraw

	img = Image.new("RGB", (1200, 1600), "#f7f3e8")
	d = ImageDraw.Draw(img)
	for y in range(120, 1560, 44):
		d.line([(80, y), (1120, y)], fill="#d8d2c0", width=1)
	d.line([(150, 60), (150, 1560)], fill="#e0a0a0", width=2)
	for i, text in enumerate(lines or ["Goal Oct to Dec", "Money: Meet Arjun Singh for PMS", "GHL turnaround: Visit leased gardens",
			"Close open loops: Ruchi ITR, Driver's licence, Anya passport", "Generic promotion ?"]):
		d.text((170, 96 + i * 88), text, fill="#2a2a5a")
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	return buf.getvalue()


def prepare_site(time_zone="Asia/Kolkata"):
	"""Make a fresh test site match lifeos.localhost: setup done, the time zone set and MCP on. Writes the singles directly,
	since the setup wizard (which would ask for language and country) never runs on a test site."""
	for field, value in {"time_zone": time_zone, "setup_complete": 1, "enable_mcp": 1, "date_format": "yyyy-mm-dd"}.items():
		frappe.db.set_single_value("System Settings", field, value)
	frappe.db.set_value("Installed Application", {"app_name": "frappe"}, "is_setup_complete", 1)
	# a new site has no encryption key until something needs one; write it now, before a web server caches the site config
	from frappe.utils.password import get_encryption_key

	get_encryption_key()
	frappe.clear_cache()
	return "Site prepared."


# ---------- test debris ----------
# Title prefixes the acceptance scripts (tools/*.mjs) give their records, each followed by the run's stamp: Date.now() in
# base 36, eight characters starting with "m" in 2026. Some carry the screen width or a number before the stamp.
DEBRIS_PREFIXES = [
	"Journal photo", "Production note", "October goal", "Birthday", "Passport", "Target note", "Source note", "Project task",
	"Project", "Old done task", "Stale open task", "Sanitise", "S3 agent item", "S3 secret", "UX door task", "UX due today",
	"UX done", "UX carried", "UX archived by the job", "UX note", "UX permit", "UX chat", "UX inbox", "UX3 area A", "UX3 area B",
	"UX3 filed under A", "UX3 due today", "UX3 open goal", "UX3 annual goal", "UX3 goal task", "UX parent", "UX child",
	"Promotion plan", "Nowrojee",
]
DEBRIS_FILE_PREFIXES = ["journal-", "production-"]
_TITLED = {
	"Life Area": "area_name", "Life Project": "title", "Life Inbox Item": "title", "Life Task": "title", "Life Note": "title",
	"Life Important Date": "title", "Life Goal": "title", "Life Vault Document": "title", "Life Chat Log": "title",
	"Life Person": "full_name", "Life Proposal": "preview",
	# UX fixes, set 5
	"Life Idea": "title", "Life Habit": "title", "Life Ask Thread": "title",
	# set 7
	"Life Exit": "title", "Life Goal Reading": "title",
}


def _stamp_re():
	import re

	prefixes = "|".join(re.escape(p.strip()) for p in sorted(DEBRIS_PREFIXES, key=len, reverse=True))
	return re.compile(rf"^(?:{prefixes})(?: \d)?(?: \d{{3,4}})? (m[0-9a-z]{{7}})(?:$|[ .])")


def find_test_debris(site_check=True):
	"""Every record the acceptance scripts left, by DocType: {doctype: set(names)}, plus the run stamps found.

	Finds titles made by the scripts, then everything that hangs off them: proposals and the records they created,
	records made from a debris inbox item, filed under a debris area, project, goal or parent note."""
	import re

	rx = _stamp_re()
	s4 = re.compile(r"^(?:S[457]|BF1) [^\n]*?\b(m[0-9a-z]{7})\b")  # sets 4, 5 and 7, bug fix 1: "S4 <what> [<width>] <stamp>"
	stamps = set()
	for dt, field in _TITLED.items():
		# nosemgrep: frappe-sql-format-injection -- development tool: DocType and field from the _TITLED constant
		for (title,) in frappe.db.sql(f"select `{field}` from `tab{dt}`"):
			m = rx.match(title or "") or s4.match(title or "")
			if m:
				stamps.add(m.group(1))
	for (fname,) in frappe.db.sql("select file_name from tabFile where attached_to_doctype like 'Life %%'"):
		for p in DEBRIS_FILE_PREFIXES:
			if (fname or "").startswith(p) and len(fname.split(".")[0]) == len(p) + 8:
				stamps.add(fname[len(p):len(p) + 8])
	debris = {dt: set() for dt in _TITLED}
	for dt, field in _TITLED.items():
		for s in stamps:
			debris[dt].update(frappe.get_all(dt, filters={field: ["like", f"%{s}%"]}, pluck="name"))
	# follow what hangs off them until nothing new turns up
	follow = [("inbox_item", "Life Inbox Item"), ("area", "Life Area"), ("project", "Life Project"), ("goal", "Life Goal"),
		("parent_note", "Life Note"), ("parent_area", "Life Area")]
	from lifeos.constants import SPACE_DOCTYPES

	for _ in range(5):
		grew = False
		for dt in SPACE_DOCTYPES:
			if dt in ("Life Index", "Life Link"):
				continue
			meta = frappe.get_meta(dt)
			for field, target in follow:
				names = debris.get(target)
				if names and meta.has_field(field):
					found = set(frappe.get_all(dt, filters={field: ["in", list(names)]}, pluck="name"))
					if found - debris.setdefault(dt, set()):
						debris[dt] |= found
						grew = True
		props = debris.get("Life Proposal") or set()
		for p in frappe.get_all("Life Proposal", filters={"name": ["in", list(props) or [""]]}, fields=["created_doctype", "created_name"]):
			if p.created_doctype and p.created_name and p.created_doctype.startswith("Life ") and frappe.db.exists(p.created_doctype, p.created_name):
				if p.created_name not in debris.setdefault(p.created_doctype, set()):
					debris[p.created_doctype].add(p.created_name)
					grew = True
		if not grew:
			break
	# keystrokes of the rename check ("…renamed") that reached quick add when the field lost focus: "n" opened it
	debris.setdefault("Life Task", set()).update(frappe.get_all("Life Task", filters={"title": "amed", "area": ["is", "not set"]}, pluck="name"))
	return {dt: names for dt, names in debris.items() if names}, sorted(stamps)


def _orphan_files():
	"""Files attached to a lifeos record that no longer exists (tests that delete their records leave these)."""
	out = []
	for (dt,) in frappe.db.sql("select distinct attached_to_doctype from tabFile where attached_to_doctype like 'Life %%'"):
		if not frappe.db.exists("DocType", dt) or not frappe.db.table_exists(dt):
			continue
		# nosemgrep: frappe-sql-format-injection -- development tool: dt is checked to be an existing DocType with a table; values are parameters
		out += frappe.db.sql(f"""select f.name, f.file_url, f.is_private from tabFile f left join `tab{dt}` r on r.name = f.attached_to_name
			where f.attached_to_doctype = %s and r.name is null""", dt, as_dict=True)
	return out


def purge_test_debris(dry_run=True):
	"""Delete the acceptance scripts' records with their proposals, links, index rows, files, child rows, versions and
	comments. With dry_run (the default) only report counts.

	Run: bench --site lifeos.localhost execute lifeos.devtools.purge_test_debris --kwargs "{'dry_run': 0}" """
	debris, stamps = find_test_debris()
	report = {dt: len(n) for dt, n in debris.items()}
	pairs = [(dt, n) for dt, names in debris.items() for n in names]
	if dry_run or not (pairs or _orphan_files()):
		return {"stamps": len(stamps), "records": report, "orphan_files": len(_orphan_files()), "dry_run": bool(dry_run)}
	month_goals = frappe.db.sql("select name from `tabLife Month Plan Goal` where " +
		" or ".join(["title like %s"] * len(stamps)), [f"%{s}%" for s in stamps]) if stamps else []
	files = []
	for dt, names in debris.items():
		names = list(names)
		if not frappe.db.exists("DocType", dt):  # created_doctype comes from proposal rows: only a real DocType names a table
			continue
		meta = frappe.get_meta(dt)
		for tf in meta.get_table_fields():
			# nosemgrep: frappe-sql-format-injection -- development tool: child table names from the meta of a checked DocType; values are parameters
			frappe.db.sql(f"delete from `tab{tf.options}` where parenttype=%s and parent in %s", (dt, names))
		frappe.db.sql("delete from `tabLife Index` where ref_doctype=%s and ref_name in %s", (dt, names))
		frappe.db.sql("delete from `tabLife Exit` where record_doctype=%s and record_name in %s", (dt, names))  # set 7
		if dt == "Life Habit":
			frappe.db.sql("delete from `tabLife Month Plan Habit` where habit in %s", (names,))
		frappe.db.sql("delete from `tabLife Link` where (from_doctype=%s and from_name in %s) or (to_doctype=%s and to_name in %s)",
			(dt, names, dt, names))
		files += frappe.get_all("File", filters={"attached_to_doctype": dt, "attached_to_name": ["in", names]}, fields=["name", "file_url", "is_private"])
		frappe.db.sql("delete from `tabVersion` where ref_doctype=%s and docname in %s", (dt, names))
		frappe.db.sql("delete from `tabComment` where reference_doctype=%s and reference_name in %s", (dt, names))
		if dt == "Life Ask Thread":
			frappe.db.sql("delete from `tabLife Ask Message` where thread in %s", (names,))
		# nosemgrep: frappe-sql-format-injection -- development tool: dt is checked to be an existing DocType; names are a parameter
		frappe.db.sql(f"delete from `tab{dt}` where name in %s", (names,))
	if month_goals:
		frappe.db.sql("delete from `tabLife Month Plan Goal` where name in %s", ([m[0] for m in month_goals],))
	files += _orphan_files()
	for f in files:
		_delete_file(f)
	# saved views that point at a debris record or a run's search
	removed_views = 0
	for v in frappe.get_all("Life View State", fields=["name", "state"]):
		state = v.state or ""
		if any(s in state for s in stamps) or any(n in state for _, n in pairs if len(n) > 6):
			frappe.db.sql("delete from `tabLife View State` where name=%s", v.name)
			removed_views += 1
	frappe.clear_cache()
	return {"stamps": len(stamps), "records": report, "month_goals": len(month_goals), "files": len(files), "views": removed_views}
