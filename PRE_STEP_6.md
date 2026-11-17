# Pre-step 6: bring Life OS up to Frappe's own conventions

Frappe publishes official agent skills for building Frappe apps (github.com/frappe/skills) and official scanning rules (github.com/frappe/semgrep-rules). Life OS was built without them. A scan on 17 November 2026 found 732 findings in `lifeos/`:

| Rule | Findings | Notes |
| --- | --- | --- |
| missing-argument-type-hint | 619 | Almost no whitelisted method has type hints; Frappe uses them to validate arguments |
| frappe-sql-format-injection | 70 | SQL built by string formatting, mostly in `api/wiki.py`, `devtools.py`, `ai/tools.py`, `api/chats.py`, `api/tasks.py`, `api/utils.py`, `ai/insights.py` |
| frappe-manual-commit | 21 | `devtools.py`, `install.py`, `loadtest.py`, `api/ask.py`, `chat_import.py`, `demo.py` |
| frappe-setuser | 16 | Mostly `loadtest.py` and `demo.py`; also `insights.py` and `chat_import.py`, which run in production |
| frappe-missing-translate-function-python | 3 | |
| frappe-security-file-traversal | 2 | `sources.py` |
| frappe-untranslated-label-in-translated-message | 1 | |

Also, 83 of 171 `@frappe.whitelist` methods do not declare `methods=[...]`.

This set fixes all of it without changing behaviour, then audits the app with Frappe's own audit and review skills. It changes no screen and adds no feature.

**This set needs set 5.** If `UX_FIXES_5_DONE` does not exist, write "Pre-step 6 needs set 5 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md` (including its new section "Frappe conventions"), `STATUS.md` and `DECISIONS.md` first. Then read these skills in `.claude/skills/` (fetched by `scripts/get-frappe-skills.sh`, which the task runner runs at the start): `frappe-app-dev`, `frappe-code-review`, `code-style`, and `deep-app-audit` with its `security/` and `quality/` folders.

## 1. The scan tool

- Add `tools/scan.sh`. It fetches `github.com/frappe/semgrep-rules` (pinned to a commit recorded in the script), and runs `semgrep scan --config <rules>/rules` over the given files, or over `lifeos/` when none are given. It must work on the owner's Mac with Docker running and nothing else installed: run semgrep inside the `lifeos-bench` container (install it there with pip if missing) or in a throwaway `lifeos-`-prefixed container. Exit non-zero on any finding.
- Save today's full result as `docs/conformance/scan-before.txt` (rule, file, line, count per rule).
- Add the scan to the end of `tools/acceptance.mjs`'s run or to the documented check list in `STATUS.md`, so every future set runs it.

## 2. Fix the findings

Fix by rule, committing after each.

- **Whitelisted methods.** Every `@frappe.whitelist` declares `methods=["GET"]` for reads and `methods=["POST"]` for anything that writes; methods that do both are split or marked POST. Check the front end and `agent/` callers use the matching HTTP method (frappe-ui `createResource`/`call` defaults; agents through MCP and REST). Every parameter has a type hint that matches what callers send. Frappe validates arguments against hints, so an integer sent as a string must be hinted to accept it (for example `int | str` converted inside, or fix the caller). Run the full unit and acceptance suites after this step; most breakage will show here.
- **SQL.** Replace string-built SQL with `frappe.qb` or `frappe.db.sql` with parameters. Where a value is genuinely an identifier (a field or table name) that cannot be a parameter, validate it against the DocType meta first and add `# nosemgrep: frappe-sql-format-injection` with one line saying why it is safe. No user-supplied value may reach SQL unparameterised. The `Life Index` FULLTEXT search must stay as fast as before (re-run the set 4 load test timings).
- **Manual commits.** Remove `frappe.db.commit()` from request handlers and from code the framework already commits. Keep it only where it is required (patches, install, long background jobs that must save progress, the load test, demo data), each with a `# nosemgrep` and the reason. Ask's streaming and chat import are the two to look at carefully: a commit inside a request can leave half-done work if the request later fails.
- **Switching user.** Remove `frappe.set_user` from production code (`insights.py`, `chat_import.py`). Run the work as the right user by passing the user explicitly and checking permissions for that user (`frappe.has_permission(..., user=...)`, permission-aware queries with that user), or enqueue the job with the user. Demo and load-test code may keep it with a `# nosemgrep` and the reason. Add a test that an insight or an import never includes a record the target user cannot read.
- **File traversal.** In `sources.py`, resolve every file path through Frappe's File records and check that the resolved path stays inside the site's private or public files folder. Add a test with a `../` path.
- **Translations.** Wrap the user-facing strings the scan names in `_()`.
- **The other two rules from `frappe-app-dev`:** confirm no user-facing code calls `frappe.qb.get_query` without `ignore_permissions=False`, and that every `has_permission` hook returns `True` or `False` on every path (never `None`). Add a unit test for each hook's paths if missing.

At the end of this step `tools/scan.sh` reports zero findings, apart from inline `nosemgrep` exceptions. List every exception in `docs/conformance/exceptions.md` with its file, rule and reason.

## 3. Deep audit

Run Frappe's `deep-app-audit` over `lifeos`:

- Use its own script with the local `claude` CLI if it runs unattended in this environment. Limit it to the security scopes and the quality rules that apply to an app with its own DocTypes (the `A-customization` rules about overriding ERPNext do not apply; skip them and say so).
- If the script cannot run unattended here, work through its `security/` and `quality/` checklists yourself, file by file, and record which checks you applied.
- Verify every candidate finding before acting on it, as the skill says. Fix every confirmed finding of severity high or above. Record the rest with a reason in `docs/conformance/audit.md`.

## 4. Review

Review the whole app against `frappe-code-review`, section by section (correctness, security, performance, concurrency, readability, API design, testing, error messages and logging). Fix what it finds that is a real defect. Note style-only points in `docs/conformance/review.md` without changing code that works, unless the change is small and safe.

## 5. Write it down

- `docs/conformance/README.md`: what was checked, the before and after counts per rule, the exceptions, the audit and review results, and how to re-run each check.
- `STATUS.md`: add a "Pre-step 6: Frappe conventions" section and the scan to the list of checks run at the end of every set.
- `DECISIONS.md`: record any behaviour that had to change (for example an API method that became POST-only) and why.

## What must not change

- Behaviour seen by the owner: every screen, route, filter, count, shortcut and agent method works as before.
- The data model, except where a fix needs a field or index; record any such change.
- Agent compatibility: `agent/SKILL.md` and `agent/fake_agent.py` keep working; if an agent method's HTTP method changes, update both and say so in `DECISIONS.md`.

## Checks

- `./tools/scan.sh` exits zero.
- All unit tests pass; new tests for user switching, file paths and permission hooks pass.
- `node tools/acceptance.mjs` passes at 1440 px and 390 px.
- The set 4 load test timings are no worse than recorded in `STATUS.md`.
- The fake agent runs end to end.

## Working rules

- Order: 1 scan tool; 2 fixes, one rule at a time; 3 audit; 4 review; 5 write-up.
- Run the unit tests after each rule's fixes and the acceptance script after the whitelist and SQL steps. Commit once per rule or step.
- When finished, create an empty file named `PRE_STEP_6_DONE` and commit.
