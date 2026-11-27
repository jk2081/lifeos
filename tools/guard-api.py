"""G1, unused API: every @frappe.whitelist method in lifeos/ must be called by a screen, a test, another file or an agent skill.

A method is used when, in any file other than the one that defines it (frontend/src, lifeos/, agent/, tools/):
  - its dotted path `lifeos.api.goals.get`, or the short form `goals.get` (a screen's api('goals.get'), a skill's text), is written out;
  - the data layer lists it: group('goals', [..., 'get', ...]) or call('goals', 'get');
  - or, for a name of its own (not a bare `get` or `list`), the name is called or imported in another Python file, or written as a string
    in a screen (a dispatcher such as weeklyAct('meeting_done') passes it on).
What is called only at run time (a hook, a scheduler, a method the agent API reaches by name) is in tools/guard-api-allow.json with a one-line reason.
Run: python3 tools/guard-api.py [root]. Exit 1 on a method nothing calls, and on an allow-list entry that is no longer needed.
"""
import ast
import json
import re
import sys
from pathlib import Path

GENERIC = {"get", "list", "set", "create", "update", "delete", "save", "read", "add", "remove", "all", "search", "run", "check", "status"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "public", "dist", "build"}
TEXT = {".py", ".js", ".mjs", ".vue", ".md", ".json", ".html", ".yml", ".yaml"}


def files(root: Path, top: str):
    base = root / top
    if not base.exists():
        return
    for p in base.rglob("*"):
        if p.is_file() and p.suffix in TEXT and not SKIP_DIRS.intersection(p.parts):
            yield p


def is_whitelist(dec: ast.expr) -> bool:
    node = dec.func if isinstance(dec, ast.Call) else dec
    return (isinstance(node, ast.Attribute) and node.attr == "whitelist") or (isinstance(node, ast.Name) and node.id == "whitelist")


def whitelisted(root: Path) -> dict:
    """{ 'lifeos.api.goals.get': 'lifeos/api/goals.py' }"""
    out = {}
    for p in files(root, "lifeos"):
        if p.suffix != ".py" or "/tests/" in p.as_posix():
            continue
        tree = ast.parse(p.read_text(encoding="utf8"))
        module = ".".join(p.relative_to(root).with_suffix("").parts)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(is_whitelist(d) for d in node.decorator_list):
                out[f"{module}.{node.name}"] = p.relative_to(root).as_posix()
    return out


def read_all(root: Path) -> dict:
    texts = {}
    for top in ("frontend/src", "lifeos", "agent", "tools"):
        for p in files(root, top):
            rel = p.relative_to(root).as_posix()
            if rel.startswith("tools/guard-api"):
                continue
            texts[rel] = p.read_text(encoding="utf8", errors="ignore")
    return texts


def used(dotted: str, defined_in: str, texts: dict) -> bool:
    module, name = dotted.rsplit(".", 1)
    ns = module.rsplit(".", 1)[-1]
    short = re.compile(rf"(?<![\w.]){re.escape(ns)}\.{re.escape(name)}\b")
    group = re.compile(rf"""group\(\s*['"]{re.escape(ns)}['"]\s*,\s*\[[^\]]*['"]{re.escape(name)}['"]""", re.S)
    call = re.compile(rf"""call\(\s*['"]{re.escape(ns)}['"]\s*,\s*['"]{re.escape(name)}['"]""")
    bare = re.compile(rf"\b{re.escape(name)}\b\s*[(,)]|import[^\n]*\b{re.escape(name)}\b")
    quoted = re.compile(rf"""['"`]{re.escape(name)}['"`]""")
    for rel, text in texts.items():
        if rel == defined_in:
            continue
        if dotted in text or short.search(text) or group.search(text) or call.search(text):
            return True
        if name not in GENERIC and rel.endswith(".py") and bare.search(text):
            return True
        if name not in GENERIC and rel.startswith("frontend/src/") and quoted.search(text):
            return True
    return False


def problems(root: Path, allow_file: Path | None = None) -> list:
    root = Path(root)
    allow_file = allow_file or root / "tools/guard-api-allow.json"
    allow = json.loads(allow_file.read_text(encoding="utf8")) if allow_file.exists() else {}
    texts = read_all(root)
    methods = whitelisted(root)
    out = []
    unused = {d for d, f in methods.items() if not used(d, f, texts)}
    for d in sorted(unused - set(allow)):
        out.append(f"{methods[d]}: {d} is whitelisted and nothing calls it; remove it, or add it to tools/guard-api-allow.json with the reason")
    for d in sorted(set(allow) - unused):
        out.append(f"tools/guard-api-allow.json: {d} is called now (or gone); remove its entry")
    return out


if __name__ == "__main__":
    found = problems(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)
    print("\n".join(found))
    sys.exit(1 if found else 0)
