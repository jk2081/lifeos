"""Import a Claude or ChatGPT data export (UX fixes, set 4): every conversation becomes a Life Chat Log, created or updated by
its original ID, with the transcript and no summary (an agent summarises later through chats.needs_summary).

The export is a .zip holding conversations.json. Claude: a list of conversations with uuid, name, created_at, updated_at and
chat_messages. ChatGPT: a list with id (or conversation_id), title, create_time, update_time, mapping (the message tree) and
current_node; the current branch is walked from current_node to the root. Unknown fields are ignored.

Everything is read first. If the file is not an export of the kind chosen, or most conversations cannot be read, the job fails
with the counts and writes nothing. Otherwise each readable conversation is written and the unreadable ones are counted."""
import datetime
import io
import json
import os
import zipfile

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

SYSTEMS = {"claude": "Claude", "chatgpt": "ChatGPT"}
MAX_ZIP = 1024 * 1024 * 1024
MAX_TRANSCRIPT = 1_000_000  # characters kept per conversation; a longer one ends with a note that it was cut
PROGRESS_TTL = 7 * 24 * 3600


class ImportFailed(Exception):
	pass


def _key(space, system):
	return f"lifeos:chat_import:{space}:{system}"


def progress(space, system):
	return frappe.cache.get_value(_key(space, system))


def _set(space, system, **values):
	cur = frappe.cache.get_value(_key(space, system)) or {}
	cur.update(values)
	frappe.cache.set_value(_key(space, system), cur, expires_in_sec=PROGRESS_TTL)
	frappe.publish_realtime("lifeos_chat_import", {"space": space, "system": system, **cur}, user=cur.get("user"))
	return cur


# ---------- reading ----------

def _when(value):
	"""An ISO string or a Unix time (ChatGPT) as a naive datetime in UTC; None when missing."""
	if value in (None, ""):
		return None
	if isinstance(value, (int, float)):
		return datetime.datetime.utcfromtimestamp(float(value))
	try:
		dt = get_datetime(str(value).replace("Z", "+00:00"))
	except Exception:
		return None
	if dt and dt.tzinfo:
		dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
	return dt


def _stamp(dt):
	return dt.strftime("%-d %b %Y %H:%M") if dt else ""


def _block(speaker, dt, text, files):
	head = f"**{speaker}**" + (f" · {_stamp(dt)}" if dt else "")
	body = (text or "").strip()
	if files:
		body += ("\n\n" if body else "") + "Attachments: " + ", ".join(sorted(set(files)))
	return head + "\n\n" + (body or "*(no text)*")


def _claude_text(m):
	if isinstance(m.get("content"), list):
		parts = [c.get("text") for c in m["content"] if isinstance(c, dict) and c.get("type") == "text" and c.get("text")]
		if parts:
			return "\n\n".join(parts)
	return m.get("text") or ""


def read_claude(conv):
	uuid = conv.get("uuid")
	if not uuid:
		raise ValueError("no uuid")
	msgs = conv.get("chat_messages")
	if msgs is None:
		raise ValueError("no chat_messages")
	blocks = []
	for m in msgs:
		who = "You" if m.get("sender") == "human" else "Claude"
		files = [a.get("file_name") for a in (m.get("attachments") or []) + (m.get("files") or []) if isinstance(a, dict) and a.get("file_name")]
		blocks.append(_block(who, _when(m.get("created_at")), _claude_text(m), files))
	created = _when(conv.get("created_at"))
	return {"external_id": str(uuid), "title": (conv.get("name") or "").strip() or "Untitled chat", "created": created,
		"updated": _when(conv.get("updated_at")) or created, "url": f"https://claude.ai/chat/{uuid}", "assistant": "Claude",
		"transcript_md": "\n\n".join(blocks)}


def read_chatgpt(conv):
	cid = conv.get("id") or conv.get("conversation_id")
	mapping = conv.get("mapping")
	if not cid or not isinstance(mapping, dict):
		raise ValueError("no id or mapping")
	node = conv.get("current_node")
	if not node or node not in mapping:  # no current branch named: the newest leaf
		leaves = [k for k, v in mapping.items() if not (v or {}).get("children")]
		node = max(leaves, key=lambda k: ((mapping[k].get("message") or {}).get("create_time") or 0), default=None)
	chain, seen = [], set()
	while node and node in mapping and node not in seen:
		seen.add(node)
		chain.append(mapping[node])
		node = mapping[node].get("parent")
	blocks = []
	for n in reversed(chain):
		m = n.get("message") or {}
		role = (m.get("author") or {}).get("role")
		if role not in ("user", "assistant"):
			continue
		content = m.get("content") or {}
		parts = [p for p in content.get("parts") or [] if isinstance(p, str) and p.strip()]
		text = "\n\n".join(parts) if parts else (content.get("text") or "")
		files = [a.get("name") for a in ((m.get("metadata") or {}).get("attachments") or []) if isinstance(a, dict) and a.get("name")]
		if not text.strip() and not files:
			continue
		blocks.append(_block("You" if role == "user" else "ChatGPT", _when(m.get("create_time")), text, files))
	created = _when(conv.get("create_time"))
	return {"external_id": str(cid), "title": (conv.get("title") or "").strip() or "Untitled chat", "created": created,
		"updated": _when(conv.get("update_time")) or created, "url": f"https://chatgpt.com/c/{cid}", "assistant": "ChatGPT",
		"transcript_md": "\n\n".join(blocks)}


READERS = {"claude": read_claude, "chatgpt": read_chatgpt}


def conversations_from_zip(path):
	"""The parsed conversations.json of an export, wherever it sits in the zip."""
	if os.path.getsize(path) > MAX_ZIP:
		raise ImportFailed(_("The file is larger than 1 GB."))
	try:
		with zipfile.ZipFile(path) as z:
			names = [n for n in z.namelist() if n.rsplit("/", 1)[-1] == "conversations.json"]
			if not names:
				raise ImportFailed(_("The file has no conversations.json. Is it a data export from Claude or ChatGPT?"))
			with z.open(sorted(names, key=len)[0]) as fh:
				data = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
	except zipfile.BadZipFile:
		raise ImportFailed(_("The file is not a .zip.")) from None
	except json.JSONDecodeError as e:
		raise ImportFailed(_("conversations.json could not be read: {0}.").format(e.msg)) from None
	if isinstance(data, dict):  # some exports wrap the list
		data = data.get("conversations") or data.get("items") or []
	if not isinstance(data, list):
		raise ImportFailed(_("conversations.json does not hold a list of conversations."))
	return data


def parse(system, data):
	"""(readable conversations, number unreadable). Fails, writing nothing, when most cannot be read."""
	read, bad = [], 0
	reader = READERS[system]
	for conv in data:
		try:
			if not isinstance(conv, dict):
				raise ValueError("not an object")
			c = reader(conv)
			if len(c["transcript_md"]) > MAX_TRANSCRIPT:
				c["transcript_md"] = c["transcript_md"][:MAX_TRANSCRIPT] + "\n\n*(The rest of this chat was cut: it is longer than a million characters.)*"
			read.append(c)
		except Exception:
			bad += 1
	if data and (not read or bad > len(data) / 2):
		raise ImportFailed(_("{0} of {1} conversations could not be read as a {2} export. Nothing was imported.").format(
			bad, len(data), SYSTEMS[system]))
	return read, bad


# ---------- writing ----------

def run(space, system, file_url, user):
	"""The background job. Progress is in the cache under the space and system, so the screen can show it after a reload."""
	from lifeos.api import chats, connections

	frappe.set_user(user)
	_set(space, system, status="Reading", done=0, total=0, created=0, updated=0, unchanged=0, skipped=0, error=None,
		started_on=str(now_datetime())[:19], finished_on=None, user=user)
	try:
		f = frappe.get_doc("File", {"file_url": file_url})
		data = conversations_from_zip(f.get_full_path())
		convs, bad = parse(system, data)
	except ImportFailed as e:
		_set(space, system, status="Failed", error=str(e), finished_on=str(now_datetime())[:19])
		return
	except Exception as e:
		frappe.log_error(title="Life OS chat import failed")
		_set(space, system, status="Failed", error=_("The file could not be read: {0}").format(str(e)[:300]), finished_on=str(now_datetime())[:19])
		return
	counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": bad}
	_set(space, system, status="Importing", total=len(convs), skipped=bad)
	in_worker = bool(getattr(frappe.local, "job", None))
	for i, c in enumerate(convs, 1):
		# one conversation that fails is undone alone; the ones before it stay
		frappe.db.savepoint("lifeos_chat_import")
		try:
			res = chats.log(space=space, title=c["title"], date=(c["created"] or now_datetime()).date(), url=c["url"], assistant=c["assistant"],
				source_system=system, external_id=c["external_id"], transcript_md=c["transcript_md"],
				updated_on=c["updated"] or c["created"])
			counts["created" if res["created"] else ("updated" if res.get("changed") else "unchanged")] += 1
		except Exception:
			counts["skipped"] += 1
			frappe.db.rollback(save_point="lifeos_chat_import")
			frappe.log_error(title="Life OS chat import: one conversation failed")
			continue
		if i % 25 == 0 or i == len(convs):
			if in_worker:  # a long job keeps what it has done, so a timeout does not lose an hour of import
				frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long background job: progress is saved every 25 conversations
			_set(space, system, done=i, **counts)
	connections.touch(space, system, _("Import of {0} chats").format(len(convs)))
	_set(space, system, status="Done", done=len(convs), finished_on=str(now_datetime())[:19], **counts)
