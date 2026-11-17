#!/usr/bin/env python3
"""Write docs/conformance/exceptions.md: every inline `nosemgrep` in the app, with its file, line, rule and reason.

  python3 tools/scan_exceptions.py           write the file
  python3 tools/scan_exceptions.py --check   exit 1 if the file is out of date
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/conformance/exceptions.md"
MARK = re.compile(r"#\s*nosemgrep:\s*([\w,\s-]+?)\s*(?:--|\(|$)\s*(.*?)\)?\s*$")
HEAD = """# Scan exceptions

Every finding of Frappe's semgrep rules that stays in the code carries an inline `# nosemgrep: <rule> -- <reason>`.
This list is written from those comments by `python3 tools/scan_exceptions.py`; do not edit it by hand.

"""


def exceptions() -> list[tuple[str, int, str, str]]:
	rows = []
	for path in sorted((ROOT / "lifeos").rglob("*.py")):
		for n, line in enumerate(path.read_text().splitlines(), 1):
			m = MARK.search(line)
			if m:
				rel = str(path.relative_to(ROOT))
				for rule in m.group(1).split(","):
					rows.append((rel, n, rule.strip(), m.group(2).strip()))
	return rows


def render(rows) -> str:
	counts = {}
	for _path, _line, rule, _why in rows:
		counts[rule] = counts.get(rule, 0) + 1
	out = [HEAD, "| Rule | Exceptions |", "| --- | --- |"]
	out += [f"| {rule} | {n} |" for rule, n in sorted(counts.items())]
	out += [f"| Total | {len(rows)} |", ""]
	for rule in sorted(counts):
		out += [f"## {rule}", "", "| File | Line | Reason |", "| --- | --- | --- |"]
		out += [f"| `{p}` | {line} | {why.replace('|', '/')} |" for p, line, r, why in rows if r == rule]
		out.append("")
	return "\n".join(out)


if __name__ == "__main__":
	text = render(exceptions())
	if "--check" in sys.argv:
		stale = not OUT.exists() or OUT.read_text() != text
		print("docs/conformance/exceptions.md is out of date: run tools/scan_exceptions.py" if stale else "up to date")
		sys.exit(1 if stale else 0)
	OUT.write_text(text)
	print(f"{len(exceptions())} exceptions written to {OUT.relative_to(ROOT)}")
