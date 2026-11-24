"""Read-only git, for the update check. Fixed argument lists, never a shell, never anything a person typed."""
import os
import subprocess

TIMEOUT = 120
MERGE = "Merge pull request"
# new files here, or a changed DocType definition, mean the update runs migrations
MIGRATION_HINTS = ("/patches/", "patches.txt")


class GitError(Exception):
	pass


def run(repo, *args, timeout=TIMEOUT):
	env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
	try:
		out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=timeout, env=env, check=False)  # noqa: S603 -- fixed arguments
	except (OSError, subprocess.TimeoutExpired) as e:
		raise GitError(f"git {args[0]} did not run: {type(e).__name__}") from e
	if out.returncode:
		raise GitError(f"git {args[0]} failed (exit {out.returncode})")
	return out.stdout.strip()


def title_of(subject, body=""):
	"""A merged pull request's title: GitHub's merge commit keeps it on the first line of the body."""
	if subject.startswith(MERGE):
		first = next((line.strip() for line in (body or "").splitlines() if line.strip()), "")
		return first or subject
	return subject


def _fields(record):
	"""A log record's four fields; the body is empty (and trimmed away) for a one-line commit."""
	parts = record.strip().split("\x1f", 3)
	return [*parts, ""][:4] if len(parts) < 4 else parts


def describe(repo, rev):
	"""{commit, short, date, title} of a commit."""
	sha, ts, subject, body = _fields(run(repo, "show", "-s", "--format=%H%x1f%cI%x1f%s%x1f%b", rev))
	return {"commit": sha, "short": sha[:7], "date": ts, "title": title_of(subject, body)}


def changes_between(repo, old, new):
	"""The merged pull requests in `old..new` (first parent, newest first): [{commit, short, date, title}]."""
	raw = run(repo, "log", "--first-parent", "--format=%H%x1f%cI%x1f%s%x1f%b%x1e", f"{old}..{new}")
	out = []
	for rec in raw.split("\x1e"):
		if rec.strip():
			sha, ts, subject, body = _fields(rec)
			out.append({"commit": sha, "short": sha[:7], "date": ts, "title": title_of(subject, body)})
	return out


def has_migrations(repo, old, new):
	files = run(repo, "diff", "--name-only", old, new).splitlines()
	return any(any(h in f for h in MIGRATION_HINTS) or ("/doctype/" in f and f.endswith(".json")) for f in files)


def remote_head(repo, remote, branch):
	"""The latest commit on the remote's branch, without downloading anything."""
	out = run(repo, "ls-remote", remote, f"refs/heads/{branch}")
	if not out:
		raise GitError(f"the remote has no branch {branch}")
	return out.split()[0]


def fetch(repo, remote, branch):
	run(repo, "fetch", "--quiet", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}")


def on_remote_branch(repo, remote, branch, commit):
	"""True when `commit` is in the history of the remote branch, as of the last fetch."""
	try:
		run(repo, "merge-base", "--is-ancestor", commit, f"refs/remotes/{remote}/{branch}")
		return True
	except GitError:
		return False
