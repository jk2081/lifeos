"""Run the Life OS agent through the live Flow server and print what happened (issue 108; evidence for docs/FLOW_TRIAL.md).

    echo "exec(open('/home/frappe/frappe-bench/apps/lifeos/tools/flow_trial.py').read(), globals()); run()" | bench --site lifeos.localhost console   (inside the lifeos-bench container)

Needs `python3 tools/fake_openai.py 8765` running beside the bench and the Flow Server up (`bench flow-server status`).
Makes a Flow Provider and Model for the fake server and one Life Task in the owner's space; nothing else.
"""
import json
import time

import frappe

OWNER, OTHER = "owner@lifeos.test", "stranger@lifeos.test"


def setup():
	frappe.set_user("Administrator")  # nosemgrep: frappe-setuser -- trial script, local bench only
	if not frappe.db.exists("Flow Provider", "openai"):
		frappe.get_doc({"doctype": "Flow Provider", "provider": "openai", "api_key": "sk-fake-not-real", "base_url": "http://127.0.0.1:8765/v1"}).insert()
	if not frappe.db.exists("Flow Model", {"title": "Fake model"}):
		frappe.get_doc({"doctype": "Flow Model", "title": "Fake model", "provider": "openai", "model_id": "openai/fake-1"}).insert()
	for user in (OWNER, OTHER):
		for role in ("Flow User",):
			u = frappe.get_doc("User", user)
			if role not in [r.role for r in u.roles]:
				u.append("roles", {"role": role})
				u.save()
	if not frappe.db.exists("Life Task", {"title": "trial: owner-only secret", "space": "Private"}):
		frappe.set_user(OWNER)  # nosemgrep: frappe-setuser -- trial script, local bench only
		frappe.get_doc({"doctype": "Life Task", "title": "trial: owner-only secret", "space": "Private"}).insert()
		frappe.set_user("Administrator")  # nosemgrep: frappe-setuser -- trial script, local bench only
	from frappe.flow.doctype.flow_skill.flow_skill import sync_skills
	from frappe.flow.lib.agent import sync_agents, sync_tools
	sync_skills(); sync_tools(); sync_agents()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the Flow Server reads the data in its own request


def ask(user, message, attachments=None):
	from frappe.flow.api import api
	frappe.set_user(user)  # nosemgrep: frappe-setuser -- trial script, local bench only
	sess = api.create_session(agent="lifeos/Life OS")
	name = sess.get("name") or sess["session"]["name"]
	r = api.run(name, message, attachments)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the Flow Server reads the data in its own request
	for _ in range(60):
		time.sleep(1)
		frappe.db.rollback()
		run = frappe.db.get_value("Flow Run", r["run"], ["status", "output", "tool_calls", "usage", "error"], as_dict=True)
		if run.status not in ("Running", "Queued", "Pending", "Paused"):
			break
	return name, run


def run():
	setup()
	for user, msg in ((OWNER, "What tasks do I have?"), (OTHER, "What tasks do I have?"), (OWNER, "make task: trial made through Flow")):
		name, r = ask(user, msg)
		print(f"\n== {user}: {msg}\nsession={name} status={r.status}\nusage={r.usage}\nerror={r.error}\ntool_calls={json.dumps(frappe.parse_json(r.tool_calls), indent=1)[:1500]}\noutput={str(r.output)[:700]}")
