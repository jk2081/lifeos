"""Build the two small synthetic chat exports used by the import tests, in the documented formats.
Run from this folder: python3 make_exports.py. It writes claude_export.zip and chatgpt_export.zip."""
import json
import zipfile

CLAUDE = [
	{"uuid": "c0ffee00-0000-4000-8000-000000000001", "name": "Blend sheet for Dalmia Gold", "created_at": "2026-10-02T09:15:00.000000Z",
		"updated_at": "2026-10-02T09:40:00.000000Z", "account": {"uuid": "acct"}, "summary": "",
		"chat_messages": [
			{"uuid": "m1", "text": "Help me lay out the blend sheet.", "sender": "human", "created_at": "2026-10-02T09:15:00Z",
				"content": [{"type": "text", "text": "Help me lay out the blend sheet."}], "attachments": [{"file_name": "blend.xlsx", "file_size": 1200}], "files": []},
			{"uuid": "m2", "text": "Here is a layout with six columns.", "sender": "assistant", "created_at": "2026-10-02T09:16:00Z",
				"content": [{"type": "text", "text": "Here is a layout with six columns: garden, grade, weight, share, cost, note."}], "attachments": [], "files": []},
		]},
	{"uuid": "c0ffee00-0000-4000-8000-000000000002", "name": "", "created_at": "2026-10-05T18:00:00Z", "updated_at": "2026-10-06T08:00:00Z",
		"chat_messages": [
			{"uuid": "m3", "text": "What is a fair trade premium?", "sender": "human", "created_at": "2026-10-05T18:00:00Z", "attachments": [], "files": []},
			{"uuid": "m4", "text": "A sum paid on top of the price for community projects.", "sender": "assistant", "created_at": "2026-10-05T18:01:00Z",
				"attachments": [], "files": [], "new_field_from_the_future": True},
		]},
	{"name": "This one has no uuid and cannot be read"},
]

CHATGPT = [
	{"id": "6730a1b2-0000-0000-0000-000000000001", "title": "Drainage plan for section 7", "create_time": 1759398000.5, "update_time": 1759401600.0,
		"current_node": "n4", "conversation_id": "6730a1b2-0000-0000-0000-000000000001",
		"mapping": {
			"root": {"id": "root", "message": None, "parent": None, "children": ["n1"]},
			"n1": {"id": "n1", "parent": "root", "children": ["n2"], "message": {"author": {"role": "system"}, "content": {"content_type": "text", "parts": [""]}}},
			"n2": {"id": "n2", "parent": "n1", "children": ["n3", "n3b"], "message": {"author": {"role": "user"}, "create_time": 1759398001,
				"content": {"content_type": "text", "parts": ["How deep should the drains be in section 7?"]}, "metadata": {"attachments": [{"name": "section7.jpg"}]}}},
			"n3b": {"id": "n3b", "parent": "n2", "children": [], "message": {"author": {"role": "assistant"}, "create_time": 1759398002,
				"content": {"content_type": "text", "parts": ["An answer on a branch that was regenerated."]}}},
			"n3": {"id": "n3", "parent": "n2", "children": ["n4"], "message": {"author": {"role": "assistant"}, "create_time": 1759398003,
				"content": {"content_type": "text", "parts": ["About 60 to 90 cm on that slope."]}}},
			"n4": {"id": "n4", "parent": "n3", "children": [], "message": {"author": {"role": "user"}, "create_time": 1759401600,
				"content": {"content_type": "text", "parts": ["Thanks."]}}},
		}},
	{"id": "6730a1b2-0000-0000-0000-000000000002", "title": "Mandir budget", "create_time": 1760000000, "update_time": 1760003600, "current_node": "a2",
		"mapping": {
			"a1": {"id": "a1", "parent": None, "children": ["a2"], "message": {"author": {"role": "user"}, "create_time": 1760000000,
				"content": {"content_type": "text", "parts": ["Draft a budget for the mandir."]}}},
			"a2": {"id": "a2", "parent": "a1", "children": [], "message": {"author": {"role": "assistant"}, "create_time": 1760000100,
				"content": {"content_type": "text", "parts": ["Here is a first draft in four parts."]}}},
		}},
	{"title": "no id and no mapping"},
]


def write(name, data, inner="conversations.json"):
	with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
		z.writestr(inner, json.dumps(data, indent=1))
		z.writestr("users.json", json.dumps([{"uuid": "acct", "full_name": "Test"}]))


if __name__ == "__main__":
	write("claude_export.zip", CLAUDE)
	write("chatgpt_export.zip", CHATGPT)
	print("written")
