# Life OS

`lifeos` is a Frappe v16 app: a personal operating system. Everything that comes in is filed by the Brain onto the owner's areas, focuses and goals, and he only decides what it could not.

## Where things are

- **What to build:** GitHub issues in `jk2081/lifeos`, built one at a time by `scripts/run-issues.sh`. How the build works: `docs/BUILDING.md`. The rules for every issue: `docs/ISSUE_RULES.md`.
- **The target design:** `docs/DIRECTION.md`. Where it differs from older documents, it wins; where an issue differs from it, the issue wins.
- **Mockups:** `mockups/v2/` (PNG, and the HTML each was rendered from in `mockups/v2/source/`, for exact colours, sizes and spacing; reference only, do not copy its structure). Older mockups in `mockups/` show earlier designs.
- **What exists and why:** `STATUS.md` (what works) and `DECISIONS.md` (every deviation, with the reason).
- **History:** `docs/history/` holds the original spec (`SPEC.md`) and the briefs of the build sets before 20 November 2026. Read them only to understand why something is the way it is.

## Rules

- **Build on the local Docker bench (`docker/`), never on a live site.** Never touch life.jaikejriwal.com or the owner's server.
- **Never write secrets** to the repo, logs, issues or pull requests.
- **Keep this repo private.**
- **Judgment is a skill with examples, not code.** Code is plumbing: records, permissions, schedules, deduplication, scoring, costs and screens.
- **Use Frappe before writing your own.** Before building anything, check whether Frappe already does it: comments, global search, versions, tags, assignments, auto repeat, notifications, files, email, OAuth (Connected App). Use it and extend it. Write your own only when it cannot, and say why in `DECISIONS.md`.
- **Prefer deleting to adding.** When an issue replaces something, remove the old code, screens, routes and tests in the same change.
- Do not read or change anything outside this repository and the local bench.
- Do not stop, restart, remove or change any Docker container, image, volume or network whose name does not start with `lifeos-`.

## Frappe conventions

Frappe publishes official agent skills at github.com/frappe/skills. `scripts/get-frappe-skills.sh` fetches them into `.claude/skills/` (the runner does this at the start of every issue). Follow them:

- **`frappe-app-dev`:** read it before writing code. Every `@frappe.whitelist` declares `methods=[...]` and a type hint on every parameter; pass `ignore_permissions=False` to `frappe.qb.get_query` in user-facing code; a `has_permission` hook returns `True` or `False`, never `None`. The skill's commands use Pilot; this repo uses the Docker bench in `docker/`, so run the equivalent `bench` commands there.
- **Scan before every commit** with Frappe's rules: `./tools/scan.sh` (Frappe's semgrep rules over the files changed). A change may not add findings. An unavoidable finding gets an inline `# nosemgrep: <rule>` with the reason.
- **`frappe-code-review`:** review the whole diff against it before finishing an issue, and fix what it finds.
- **`code-style`** and **`ui-design`:** apply where they do not conflict with `frontend/COMPONENTS.md`, which wins for the front end.
- Tests subclass `IntegrationTestCase` from `frappe.tests` and run against the real database.
