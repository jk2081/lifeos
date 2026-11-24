#!/usr/bin/env python3
"""The Life OS connector: a small script an agent runs beside itself. It changes nothing in the agent's own code.

    export LIFEOS_URL=https://your-life-os  LIFEOS_API_KEY=...  LIFEOS_API_SECRET=...
    python3 connector.py --home /path/to/agent/files --system my-agent --space "My Space"           # report, pull, apply, confirm once
    python3 connector.py --home ... --system ... --loop                                              # then every 15 minutes, and a full report once a day

It reads the agent's files in --home (formats in README.md), sends them to Life OS (`agent_connector.report`), picks up what the owner changed
there (`agent_connector.pull`), applies each change to the files, and confirms (`agent_connector.confirm`), saying why when one cannot be applied.
Only the Python standard library is needed. Credentials are read from the environment and never printed.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class Life:
	def __init__(self, url, key, secret):
		self.url, self.auth = url.rstrip("/"), f"token {key}:{secret}"

	def call(self, method, get=False, **args):
		url, headers = f"{self.url}/api/method/lifeos.api.agent_connector.{method}", {"Authorization": self.auth, "Accept": "application/json"}
		args = {k: v for k, v in args.items() if v is not None}
		if get:
			req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(args)}", headers=headers, method="GET")
		else:
			headers["Content-Type"] = "application/json"
			req = urllib.request.Request(url, data=json.dumps(args).encode(), headers=headers, method="POST")
		try:
			with urllib.request.urlopen(req, timeout=60) as res:
				return json.loads(res.read().decode()).get("message")
		except urllib.error.HTTPError as e:
			raise RuntimeError(f"{method} failed with HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def read_json(path, default):
	try:
		return json.loads(Path(path).read_text())
	except (OSError, ValueError):
		return default


def fact_id(f):
	return str(f.get("id") or hashlib.sha1(str(f.get("text", "")).encode()).hexdigest()[:12])


def snapshot(home: Path) -> dict:
	"""What the agent holds: memory.json (facts), jobs.json, skills/<name>/SKILL.md (first line after the title is the description), settings.json, actions.json."""
	facts = [{**f, "id": fact_id(f)} for f in read_json(home / "memory.json", []) if isinstance(f, dict) and f.get("text")]
	skills = []
	for md in sorted((home / "skills").glob("*/SKILL.md")) if (home / "skills").is_dir() else []:
		lines = [ln.strip() for ln in md.read_text().splitlines() if ln.strip() and not ln.startswith(("#", "---"))]
		skills.append({"name": md.parent.name, "description": lines[0][:200] if lines else ""})
	return {"facts": facts, "jobs": read_json(home / "jobs.json", []), "skills": skills, "settings": read_json(home / "settings.json", {}), "actions": read_json(home / "actions.json", [])}


def apply_change(home: Path, change: dict) -> None:
	"""Apply one change from Life OS to the agent's files; raises with a plain reason when it cannot."""
	kind, target, payload = change["kind"], change["target"], change.get("payload") or {}
	if kind in ("Fact edit", "Fact delete"):
		facts = read_json(home / "memory.json", [])
		hit = next((f for f in facts if fact_id(f) == target), None)
		if hit is None:
			raise RuntimeError("That fact is no longer in the agent's memory")
		if kind == "Fact delete":
			facts.remove(hit)
		else:
			hit["id"], hit["text"] = target, payload["text"]  # the id stays, so the next report is the same fact
		(home / "memory.json").write_text(json.dumps(facts, indent=1))
	elif kind in ("Job pause", "Job resume"):
		jobs = read_json(home / "jobs.json", [])
		hit = next((j for j in jobs if str(j.get("id")) == target), None)
		if hit is None:
			raise RuntimeError("That job is not in the agent's schedule")
		hit["paused"] = kind == "Job pause"
		(home / "jobs.json").write_text(json.dumps(jobs, indent=1))
	elif kind == "Setting":
		settings = read_json(home / "settings.json", {})
		settings.setdefault("abilities", {})[target] = payload["mode"]
		(home / "settings.json").write_text(json.dumps(settings, indent=1))
	else:
		raise RuntimeError(f"Do not know how to apply {kind}")


def run_once(life: Life, home: Path, system: str, space: str | None) -> dict:
	"""Pick up and apply what the owner changed first, so the report that follows says what is true now; then report, then confirm."""
	pulled = life.call("pull", get=True, source_system=system, space=space)
	results = []
	for ch in pulled["changes"]:
		try:
			apply_change(home, ch)
			results.append({"id": ch["id"], "status": "applied"})
		except Exception as e:  # noqa: BLE001 - whatever stops a change is the reason shown to the owner
			results.append({"id": ch["id"], "status": "failed", "reason": str(e)[:300]})
	snap = snapshot(home)
	report = life.call("report", source_system=system, space=space, **snap)
	life.call("confirm", source_system=system, space=space, changes=results, delivered=[d["id"] for d in pulled["decisions"]])
	return {"applied": sum(r["status"] == "applied" for r in results), "failed": sum(r["status"] == "failed" for r in results), "report": report["changed"],
		"decisions": pulled["decisions"]}


def main():
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("--home", required=True, help="the folder with the agent's files")
	ap.add_argument("--system", required=True, help="the agent's key in Life OS (its source_system)")
	ap.add_argument("--space", default=None)
	ap.add_argument("--loop", action="store_true", help="keep running: every 15 minutes")
	args = ap.parse_args()
	try:
		life = Life(os.environ["LIFEOS_URL"], os.environ["LIFEOS_API_KEY"], os.environ["LIFEOS_API_SECRET"])
	except KeyError as e:
		sys.exit(f"Set {e.args[0]} first (see README.md).")
	home = Path(args.home)
	while True:
		print(json.dumps(run_once(life, home, args.system, args.space)))
		if not args.loop:
			return
		time.sleep(15 * 60)


if __name__ == "__main__":
	main()
