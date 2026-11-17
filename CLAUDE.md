# Life OS

This repo will hold `lifeos`, a Frappe v16 app. It is empty apart from the spec and mockups.

- **Read `SPEC.md` in full before writing any code.** It is the single source of truth. Where a later section overrides an earlier table, the spec says so.
- **Match the mockups in `mockups/`.** PNGs show the approved look. `mockups/source/` holds the HTML they were rendered from, for exact colours, sizes and spacing. That HTML uses a design-tool template format and is reference only; do not copy its structure into the app.
- **Build on a local bench, never on a live site.** Use Docker for Frappe v16 and a throwaway test site.
- **Follow the milestone order in section 14.** Finish each milestone with its tests passing, commit with the milestone number in the message, and update `STATUS.md`.
- **Record every deviation from the spec in `DECISIONS.md`**, with the reason.
- **Never write secrets** to the repo, logs or docs.
- The spec contains the owner's personal goals as seed data. Keep this repo private.
- **This build runs unattended.** Do not ask questions. When finished, create `BUILD_DONE`. If you cannot go further, write the reason to `BUILD_BLOCKED`. `scripts/start-build.sh` restarts you with `CONTINUE_PROMPT.md` until one of those files exists.
- Do not read or change anything outside this repository and the local bench you create for it.

## Frappe conventions (from 17 November 2026)

Frappe publishes official agent skills at github.com/frappe/skills. `scripts/get-frappe-skills.sh` fetches them into `.claude/skills/` (the task runner does this at the start of every run). Follow them in every set:

- **`frappe-app-dev`**: read it before writing code. In particular: every `@frappe.whitelist` declares `methods=[...]` and a type hint on every parameter; pass `ignore_permissions=False` to `frappe.qb.get_query` in user-facing code; a `has_permission` hook returns `True` or `False`, never `None`. The skill's commands use Pilot; this repo uses the Docker bench in `docker/`, so run the equivalent `bench` commands there.
- **Scan before every commit** with Frappe's rules: `./tools/scan.sh` (Frappe's semgrep rules over the files changed). A change may not add findings. An unavoidable finding gets an inline `# nosemgrep: <rule>` with the reason.
- **`frappe-code-review`**: review every set's whole diff against it before creating the set's `_DONE` file, and fix what it finds.
- **`code-style`** and **`ui-design`**: apply where they do not conflict with `frontend/COMPONENTS.md`, which wins for the front end.
- Tests subclass `IntegrationTestCase` from `frappe.tests` and run against the real database.
