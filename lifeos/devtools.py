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
	frappe.db.commit()
	return "Users ready."


def agent_api_key(user=AGENT):
	"""Create an API key and secret for an agent user and print them once. Never stored in the repo."""
	doc = frappe.get_doc("User", user)
	secret = frappe.generate_hash(length=15)
	if not doc.api_key:
		doc.api_key = frappe.generate_hash(length=15)
	doc.api_secret = secret
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return f"{doc.api_key}:{secret}"


def purge_space(space, drop=False):
	"""Delete every lifeos record in a space with plain SQL. For test spaces only."""
	from lifeos.constants import SPACE_DOCTYPES

	for dt in SPACE_DOCTYPES:
		meta = frappe.get_meta(dt)
		for tf in meta.get_table_fields():
			frappe.db.sql(
				f"delete c from `tab{tf.options}` c join `tab{dt}` p on p.name = c.parent where c.parenttype=%s and p.space=%s", (dt, space))
		frappe.db.sql(f"delete from `tab{dt}` where space=%s", space)
	frappe.db.sql("delete from `tabEvent` where life_space=%s", space)
	if drop:
		frappe.db.sql("delete from `tabLife Space Member` where parent=%s", space)
		frappe.db.sql("delete from `tabLife Space` where name=%s", space)


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
