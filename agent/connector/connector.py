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


def is_hermes(home: Path) -> bool:
	"""Hermes keeps its memory as Markdown in memories/, not memory.json."""
	return (home / "memories" / "MEMORY.md").exists() and not (home / "memory.json").exists()


# Hermes: memories/MEMORY.md (its own notes) and memories/USER.md (about the owner), entries separated by a line holding only §.
HERMES_MEMORY = (("MEMORY.md", "Hermes memory"), ("USER.md", "Hermes, about you"))
SEPARATOR = "\n§\n"


def hermes_entries(path: Path) -> list[str]:
	try:
		text = path.read_text()
	except OSError:
		return []
	out, cur = [], []
	for line in text.splitlines():
		if line.strip() == "§":
			out.append("\n".join(cur).strip())
			cur = []
		else:
			cur.append(line)
	out.append("\n".join(cur).strip())
	return [e for e in out if e]


def write_locked(path: Path, text: str) -> None:
	"""Write a Hermes file while holding its .lock, as Hermes itself does, so the two never write at once."""
	import fcntl

	with open(path.with_name(path.name + ".lock"), "a") as lock:
		fcntl.flock(lock, fcntl.LOCK_EX)
		tmp = path.with_name(path.name + ".lifeos-tmp")
		tmp.write_text(text)
		tmp.replace(path)


def hermes_jobs(home: Path) -> tuple[list, object]:
	"""cron/jobs.json as a list of jobs, and the raw value to write back ({"jobs": [...]} or a list)."""
	raw = read_json(home / "cron" / "jobs.json", [])
	jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
	return [j for j in jobs if isinstance(j, dict)], raw


def job_row(j: dict) -> dict:
	schedule = j.get("schedule")
	if isinstance(schedule, dict):
		schedule = schedule.get("display") or schedule.get("expr") or json.dumps(schedule)
	paused = j.get("paused") if "paused" in j else (j.get("enabled") is False)
	return {"id": str(j.get("id") or j.get("name")), "name": str(j.get("name") or j.get("prompt") or "")[:140], "schedule": str(schedule or ""),
		"next_run": str(j.get("next_run_at") or j.get("next_run") or ""), "paused": bool(paused)}


def skill_rows(home: Path) -> list:
	"""Every SKILL.md under skills/, one or two folders deep (Hermes groups them: skills/<group>/<name>/SKILL.md)."""
	root, out = home / "skills", []
	if not root.is_dir():
		return out
	for md in sorted([*root.glob("*/SKILL.md"), *root.glob("*/*/SKILL.md")]):
		text = md.read_text(errors="replace")
		desc = next((ln.split(":", 1)[1].strip().strip("\"'") for ln in text.splitlines() if ln.startswith("description:")), "")
		if not desc:
			lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith(("#", "---")) and ":" not in ln[:20]]
			desc = lines[0] if lines else ""
		out.append({"name": md.parent.name, "description": desc[:200]})
	return out


def settings_file(home: Path) -> Path:
	# Hermes has no switches of its own for what it may do; Life OS's are kept beside its files, for its Life OS skill to read
	return home / ("lifeos-settings.json" if is_hermes(home) else "settings.json")


def snapshot(home: Path) -> dict:
	"""What the agent holds: its facts, jobs, skills, settings and actions (formats in README.md; Hermes's own layout is read as it is)."""
	if is_hermes(home):
		facts = [{"id": fact_id({"text": e}), "text": e, "origin": origin, "learned_on": None}
			for name, origin in HERMES_MEMORY for e in hermes_entries(home / "memories" / name)]
		jobs = [job_row(j) for j in hermes_jobs(home)[0]]
		actions = []
	else:
		facts = [{**f, "id": fact_id(f)} for f in read_json(home / "memory.json", []) if isinstance(f, dict) and f.get("text")]
		jobs = read_json(home / "jobs.json", [])
		actions = read_json(home / "actions.json", [])
	return {"facts": facts, "jobs": jobs, "skills": skill_rows(home), "settings": read_json(settings_file(home), {}), "actions": actions}


def apply_hermes_fact(home: Path, kind: str, target: str, payload: dict) -> None:
	for name, _origin in HERMES_MEMORY:
		path = home / "memories" / name
		entries = hermes_entries(path)
		for i, e in enumerate(entries):
			if fact_id({"text": e}) == target:
				if kind == "Fact delete":
					entries.pop(i)
				else:
					entries[i] = payload["text"].strip()
				write_locked(path, SEPARATOR.join(entries) + ("\n" if entries else ""))
				return
	raise RuntimeError("That fact is no longer in the agent's memory")


def apply_change(home: Path, change: dict) -> None:
	"""Apply one change from Life OS to the agent's files; raises with a plain reason when it cannot."""
	kind, target, payload = change["kind"], change["target"], change.get("payload") or {}
	hermes = is_hermes(home)
	if kind in ("Fact edit", "Fact delete") and hermes:
		apply_hermes_fact(home, kind, target, payload)
	elif kind in ("Fact edit", "Fact delete"):
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
		path = home / "cron" / "jobs.json" if hermes else home / "jobs.json"
		jobs, raw = hermes_jobs(home) if hermes else (read_json(path, []), None)
		hit = next((j for j in jobs if str(j.get("id") or j.get("name")) == target), None)
		if hit is None:
			raise RuntimeError("That job is not in the agent's schedule")
		if hermes and "enabled" in hit:
			hit["enabled"] = kind == "Job resume"
		else:
			hit["paused"] = kind == "Job pause"
		out = raw if hermes and isinstance(raw, dict) else jobs
		if hermes:
			write_locked(path, json.dumps(out, indent=2))
		else:
			path.write_text(json.dumps(out, indent=1))
	elif kind == "Setting":
		settings = read_json(settings_file(home), {})
		settings.setdefault("abilities", {})[target] = payload["mode"]
		settings_file(home).write_text(json.dumps(settings, indent=1))
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
