"""Summarise semgrep JSON from stdin for tools/scan.sh: one line per finding, then counts per rule.

Exits 1 on any finding or semgrep error. With --quiet, prints only the counts (to stderr).
"""

import collections
import json
import sys


def main() -> int:
	quiet = "--quiet" in sys.argv
	data = json.load(sys.stdin)
	results = data.get("results", [])
	errors = [e for e in data.get("errors", []) if e.get("level") == "error"]
	counts = collections.Counter()
	out = sys.stderr if quiet else sys.stdout
	for r in sorted(results, key=lambda r: (rule_of(r), r["path"], r["start"]["line"])):
		counts[rule_of(r)] += 1
		if not quiet:
			print(f"{rule_of(r)}\t{r['path']}:{r['start']['line']}")
	print("\nFindings per rule:", file=out)
	for rule, n in counts.most_common():
		print(f"  {n:5d}  {rule}", file=out)
	print(f"  {len(results):5d}  total", file=out)
	for e in errors:
		print("semgrep error:", str(e.get("message", e))[:300], file=sys.stderr)
	return 1 if results or errors else 0


def rule_of(result: dict) -> str:
	return result["check_id"].split(".")[-1]


if __name__ == "__main__":
	sys.exit(main())
