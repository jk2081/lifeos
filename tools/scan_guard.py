"""A guard for tools/scan.sh: a read or write that skips Frappe's permissions needs a reason.

A line with `ignore_permissions=True` (or `flags.ignore_permissions = True`) anywhere under lifeos/ outside tests, and a line
with `frappe.get_all(` under lifeos/api/, must carry `# system: <reason>` on the same line.
Usage: scan_guard.py [FILE_OR_DIR...]  (default lifeos). Prints one line per finding; exits 1 on any.
"""

import pathlib
import re
import sys

GET_ALL = re.compile(r"frappe\.get_all\(")
IGNORE = re.compile(r"ignore_permissions\s*=\s*(True|1)\b")
REASON = re.compile(r"#\s*system:\s*\S")


def findings(paths) -> list[str]:
	out = []
	for path in files(paths):
		posix = path.as_posix()
		if "/tests/" in posix or "lifeos/" not in posix:
			continue
		in_api = "lifeos/api/" in posix
		for n, line in enumerate(path.read_text().splitlines(), 1):
			code = line.split("#", 1)[0]
			if (IGNORE.search(code) or (in_api and GET_ALL.search(code))) and not REASON.search(line):
				out.append(f"permissions-bypass-without-reason\t{path.as_posix()}:{n}")
	return out


def files(paths):
	for p in map(pathlib.Path, paths):
		if p.is_dir():
			yield from sorted(p.rglob("*.py"))
		else:
			yield p


def main() -> int:
	found = findings(sys.argv[1:] or ["lifeos"])
	for line in found:
		print(line)
	if found:
		print(f"\n{len(found)} ignore_permissions=True or (under lifeos/api/) frappe.get_all( without a `# system: <reason>` comment on the line", file=sys.stderr)
	return 1 if found else 0


if __name__ == "__main__":
	sys.exit(main())
