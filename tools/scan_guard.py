"""A guard for tools/scan.sh: a read or write that skips Frappe's permissions needs a reason.

Under lifeos/api/, a line with `frappe.get_all(` or `ignore_permissions=True` must carry `# system: <reason>` on the
same line. Usage: scan_guard.py [FILE_OR_DIR...]  (default lifeos/api). Prints one line per finding; exits 1 on any.
"""

import pathlib
import re
import sys

BYPASS = re.compile(r"frappe\.get_all\(|ignore_permissions\s*=\s*True")
REASON = re.compile(r"#\s*system:\s*\S")


def findings(paths) -> list[str]:
	out = []
	for path in files(paths):
		if "lifeos/api/" not in path.as_posix():
			continue
		for n, line in enumerate(path.read_text().splitlines(), 1):
			code = line.split("#", 1)[0]
			if BYPASS.search(code) and not REASON.search(line):
				out.append(f"permissions-bypass-without-reason\t{path.as_posix()}:{n}")
	return out


def files(paths):
	for p in map(pathlib.Path, paths):
		if p.is_dir():
			yield from sorted(p.rglob("*.py"))
		else:
			yield p


def main() -> int:
	found = findings(sys.argv[1:] or ["lifeos/api"])
	for line in found:
		print(line)
	if found:
		print(f"\n{len(found)} frappe.get_all( or ignore_permissions=True without a `# system: <reason>` comment on the line", file=sys.stderr)
	return 1 if found else 0


if __name__ == "__main__":
	sys.exit(main())
