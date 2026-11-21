"""Skills: Life OS's own judgment, as plain-language instructions that run in background jobs. Code is plumbing."""


def eval(skill: str, live: bool = True):
	"""Run a skill's examples against the real model with the owner's key, and print each result.

	bench --site SITE execute lifeos.skills.eval --kwargs "{'skill': 'process-capture'}"
	"""
	import frappe

	from lifeos.skills import examples

	results = examples.run_all(skill, live=bool(live))
	for r in results:
		print(("PASS " if r["passed"] else "FAIL ") + r["title"] + (f" ({r['error']})" if r.get("error") else ""))
		for c in r["checks"]:
			if not c["passed"]:
				print("   failed:", c["check"], c["detail"])
	print(f"{sum(r['passed'] for r in results)} of {len(results)} pass")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- bench execute: keep the examples' last result
	return results


def record(skill: str):
	"""Run a built-in skill's examples against the real model and write each answer into its fixture file, for CI to replay.

	bench --site SITE execute lifeos.skills.record --kwargs "{'skill': 'process-capture'}"
	"""
	from lifeos.skills import examples

	return examples.record(skill)
