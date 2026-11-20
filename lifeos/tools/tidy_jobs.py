"""Issue 9: work filed before issue 8 and items failed by the intent refusal fixed in issue 6.

A job an agent filed as one item holds its inputs beside its outputs. A file on such an item that is also attached to another
item of the space, or that a reusable asset already holds, looks like an input: it moves to a reusable asset (a Just keep
item, as lifeos.api.jobs.file_job keeps one) and the item links it in `job_inputs`, so the item keeps only its outputs."""
import re

import frappe
from frappe.utils import now_datetime

from lifeos import files, permissions

ITEM = "Life Inbox Item"
AGENT_SYSTEMS = ("hermes", "claude", "agent", "chatgpt")
# the refusals of submit_result for an item's intent, as an agent passed them on to fail_item
INTENT_REFUSAL = re.compile(r"\bintent\b|kept only", re.IGNORECASE)


class MixedJobs:
	def __init__(self, log, spaces):
		self.log, self.spaces = log, spaces
		self._agents = {}

	def find(self):
		"""Items from an agent with both input-looking files and other files (the outputs)."""
		out = []
		for item in frappe.get_all(ITEM, filters={"intent": ["!=", "Just keep"], "space": ["in", self.spaces]},
				fields=["name", "title", "space", "owner", "source_system"], order_by="creation asc"):
			if not self._from_agent(item):
				continue
			current = _current_files(item.name)
			inputs = [f for f in current if self._looks_like_input(item, f)]
			outputs = [f for f in current if f not in inputs]
			if inputs and outputs:
				out.append({"item": item.name, "title": item.title, "space": item.space,
					"inputs": [_file(f) for f in inputs], "outputs": [_file(f) for f in outputs]})
		return out

	def refile(self, job):
		"""Move the job's input files to reusable assets and link them; its outputs stay on the item."""
		item = frappe.get_doc(ITEM, job["item"])
		for f in job["inputs"]:
			asset = self._asset_for(item, f)
			if asset is None:
				continue
			label = f["file_name"]
			if not any(r.label == label for r in item.job_inputs):
				item.append("job_inputs", {"label": label, "reusable_as": asset.external_id, "asset": asset.name, "file": None})
			self.log(ITEM, item.name, f"Input {label} moved to the reusable asset {asset.name} ({asset.external_id}).")
		if not item.job_id:
			item.job_id = _job_id(item)
		item.save(ignore_permissions=True)

	# ---------- finding ----------

	def _from_agent(self, item):
		if (item.source_system or "").lower() in AGENT_SYSTEMS:
			return True
		if item.owner not in self._agents:
			self._agents[item.owner] = permissions.is_agent(item.owner)
		return self._agents[item.owner]

	def _looks_like_input(self, item, f):
		"""Also attached, as a current file, to another item of the space (a reusable asset is one)."""
		others = frappe.get_all("File", filters={"attached_to_doctype": ITEM, "attached_to_name": ["!=", item.name],
			"life_sha256": f.life_sha256, "attached_to_field": ["is", "not set"], "life_version_of": ["is", "not set"]},
			pluck="attached_to_name")
		return any(frappe.db.get_value(ITEM, o, "space") == item.space for o in others)

	# ---------- moving ----------

	def _asset_for(self, item, f):
		"""The asset that now holds this input: one already holding its bytes, else a new one the file moves to."""
		asset_file = _asset_file(item.space, f["life_sha256"])
		if asset_file:
			if asset_file.file_url != frappe.db.get_value("File", f["file"], "file_url"):  # the merge may have relinked it
				self.log(ITEM, item.name, f"Input {f['file_name']} left on the item: its stored copy is not the asset's.")
				return None
			for name in frappe.get_all("File", filters={"life_version_of": f["file"]}, pluck="name"):
				frappe.db.set_value("File", name, {"attached_to_name": asset_file.attached_to_name,
					"life_version_of": asset_file.name}, update_modified=False)
			frappe.delete_doc("File", f["file"], ignore_permissions=True, force=True)
			return frappe.get_doc(ITEM, asset_file.attached_to_name)
		asset = _new_asset(item, f)
		for name in [f["file"]] + frappe.get_all("File", filters={"life_version_of": f["file"]}, pluck="name"):
			frappe.db.set_value("File", name, "attached_to_name", asset.name, update_modified=False)
		self.log(ITEM, asset.name, f"Kept as a reusable input of {item.name} ({item.title}).")
		return asset


class FailedIntents:
	def __init__(self, log, spaces):
		self.log, self.spaces = log, spaces

	def find(self):
		rows = frappe.get_all(ITEM, filters={"status": "Failed", "space": ["in", self.spaces]}, fields=["name", "title", "space", "intent", "error"],
			order_by="creation asc")
		return [dict(r) for r in rows if INTENT_REFUSAL.search(r.error or "")]

	def reset(self, row):
		"""Back to New, so an agent claims it again. Its proposals stay: tidying never deletes one."""
		item = frappe.get_doc(ITEM, row["name"])
		item.status, item.error, item.claimed_by, item.claimed_on = "New", None, None, None
		item.save(ignore_permissions=True)
		self.log(ITEM, item.name, f"Failed by the intent refusal ({(row['error'] or '')[:120]}); put back to New.")


def _current_files(item):
	"""The item's own current files: not a preview, an earlier version or an input it already lists."""
	inputs = set(files.job_input_files(item))
	rows = frappe.get_all("File", filters={"attached_to_doctype": ITEM, "attached_to_name": item, "attached_to_field": ["is", "not set"],
		"life_version_of": ["is", "not set"], "life_sha256": ["is", "set"]},
		fields=["name", "file_name", "file_url", "life_sha256"], order_by="creation asc")
	return [r for r in rows if r.name not in inputs]


def _file(row):
	return {"file": row.name, "file_name": row.file_name, "file_url": row.file_url, "life_sha256": row.life_sha256}


def _asset_file(space, digest):
	"""The current File row of a reusable asset of the space (a Just keep item with an id) that holds these bytes."""
	for row in frappe.get_all("File", filters={"attached_to_doctype": ITEM, "life_sha256": digest, "attached_to_field": ["is", "not set"],
			"life_version_of": ["is", "not set"]}, fields=["name", "file_url", "attached_to_name"], order_by="creation asc"):
		asset = frappe.db.get_value(ITEM, row.attached_to_name, ["space", "intent", "external_id"], as_dict=True)
		if asset and asset.space == space and asset.intent == "Just keep" and asset.external_id:
			return row
	return None


def _new_asset(item, f):
	from lifeos.api.jobs import _find_asset

	base = frappe.scrub(f["file_name"].rsplit(".", 1)[0]).replace("_", "-")[:120] or "input"
	reusable_as = base
	if _find_asset(item.space, reusable_as):
		reusable_as = f"{base}-{f['life_sha256'][:8]}"
	asset = frappe.get_doc({"doctype": ITEM, "space": item.space, "title": f["file_name"].rsplit(".", 1)[0][:140] or base,
		"source_type": "Upload", "intent": "Just keep", "status": "Done", "source_system": item.source_system or "agent",
		"external_id": reusable_as, "area": item.area, "claimed_by": "Administrator", "claimed_on": now_datetime(),
		"summary_md": f"Kept as a reusable input ({reusable_as}), by the tidy command from {item.title}."})
	asset.insert(ignore_permissions=True)
	return asset


def _job_id(item):
	"""The id the job is found by again (lifeos.api.jobs.file_job): its external_id when free, else the item's name."""
	if item.external_id and not frappe.db.exists(ITEM, {"space": item.space, "job_id": item.external_id, "name": ["!=", item.name]}):
		return item.external_id
	return item.name
