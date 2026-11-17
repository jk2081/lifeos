#!/usr/bin/env python3
"""Write frontend/src/lib/getMethods.json: every whitelisted Life OS method that answers only GET.

The front end (lib/api.js) and the acceptance script send these as GET and everything else as POST. Run it after
changing a `@frappe.whitelist(methods=...)`; the unit test test_pre6_conventions fails while the file is stale.
  python3 scripts/http-methods.py           write the file
  python3 scripts/http-methods.py --check   exit 1 if the file is stale
"""

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend/src/lib/getMethods.json"


def get_methods(root: pathlib.Path = ROOT) -> list[str]:
	out = []
	for path in sorted((root / "lifeos").rglob("*.py")):
		if "tests" in path.parts:
			continue
		module = ".".join(path.relative_to(root).with_suffix("").parts)
		for node in ast.parse(path.read_text(), str(path)).body:
			if isinstance(node, ast.FunctionDef) and http_methods(node) == ["GET"]:
				out.append(f"{module}.{node.name}")
	return out


def http_methods(fn: ast.FunctionDef) -> list[str] | None:
	for deco in fn.decorator_list:
		if isinstance(deco, ast.Call) and ast.unparse(deco.func) == "frappe.whitelist":
			for kw in deco.keywords:
				if kw.arg == "methods":
					return ast.literal_eval(kw.value)
			return []
	return None


def render(methods: list[str]) -> str:
	return json.dumps(methods, indent=1) + "\n"


if __name__ == "__main__":
	text = render(get_methods())
	if "--check" in sys.argv:
		stale = not OUT.exists() or OUT.read_text() != text
		print("frontend/src/lib/getMethods.json is stale: run scripts/http-methods.py" if stale else "up to date")
		sys.exit(1 if stale else 0)
	OUT.write_text(text)
	print(f"{len(json.loads(text))} GET methods written to {OUT.relative_to(ROOT)}")
