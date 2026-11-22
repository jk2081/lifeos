# Frappe conformance (pre-step 6)

On 17 November 2026 Life OS was brought up to Frappe's own conventions: the official agent skills (github.com/frappe/skills: `frappe-app-dev`, `frappe-code-review`, `code-style`, `deep-app-audit`) and the official scanning rules (github.com/frappe/semgrep-rules). Nothing on any screen changed, and no feature was added. Behaviour that had to change is listed in `DECISIONS.md` under "Pre-step 6".

## What was checked

| Check | Tool | Result |
| --- | --- | --- |
| Frappe's semgrep rules over `lifeos/` | `tools/scan.sh` | 732 findings before, **0** after; 90 inline exceptions with a reason |
| Every `@frappe.whitelist` declares `methods` and hints every argument | `test_pre6_conventions` | 171 of 171 (78 GET, 93 POST) |
| `frappe.qb.get_query` in user-facing code passes `ignore_permissions=False` | read the code | the app never calls it |
| Every `has_permission` hook answers True or False on every path | `test_pre6_fixes.TestPermissionHooksAnswerTrueOrFalse` | 7 hooks, every user and permission type |
| Deep audit: security and correctness | `deep-app-audit` checklists, by hand | 10 distinct findings confirmed; the 3 High, and 1 Moderate of the same kind as one of them, fixed: [audit.md](audit.md) |
| Code review, sections 1 to 8 | `frappe-code-review` | 6 real defects (and Today's slow counts) fixed; style points noted: [review.md](review.md) |

## The scan, before and after

| Rule | Before | After | Exceptions |
| --- | ---: | ---: | ---: |
| missing-argument-type-hint | 619 | 0 | 0 |
| frappe-sql-format-injection | 70 | 0 | 69 |
| frappe-manual-commit | 21 | 0 | 5 |
| frappe-setuser | 16 | 0 | 13 |
| frappe-missing-translate-function-python | 3 | 0 | 0 |
| frappe-security-file-traversal | 2 | 0 | 3 |
| frappe-untranslated-label-in-translated-message | 1 | 0 | 0 |
| **Total** | **732** | **0** | **90** |

Also, 83 of 171 whitelisted methods had no `methods=[...]`; now none lack it. The full list before is [scan-before.txt](scan-before.txt). Every exception is in [exceptions.md](exceptions.md), with its file, line, rule and reason. They fall into four groups:

- **SQL put together from fixed fragments:** lists, counts and full-text search, where the columns are checked against the DocType meta and every value is a parameter. No caller or model value reaches SQL unparameterised.
- **Commits that must stay:** `after_install`, the load test's seeding and removal, and the chat import's progress inside a worker job.
- **`set_user` in demo data and the load test**, which act as the owner, the agent or a member on purpose.
- **`open()` on files in a known place:** a temporary folder the code made, or a path `files.local_path` has checked.

## What was fixed, in short

- **Whitelisted methods.** Every method answers either GET or POST. The front end, the acceptance script and the fake agent send reads as GET (`frontend/src/lib/getMethods.json`, written by `scripts/http-methods.py`). On the acceptance site, GETs run in a read-only transaction (`lifeos/strict_get.py`), so a read that writes fails the run.
- **Commits.** Ask keeps its streamed text in the cache and commits once. Chat import and the nightly insights use savepoints, which fixed a chat import that could silently lose up to 24 conversations.
- **User switching.** The nightly insights and the chat import never switch the session's user. Records are checked for the user the work is for.
- **Files.** Originals are read only from inside the site's files folders. A `../` path or a symbolic link out of the folder is refused.
- **Audit.** Fixed: Reset's undo trusted the browser's undo log; agents could list the sources of closed Vault documents, and see deleted Vault documents in the trash; and every task accepted from review could not be deleted.
- **Review.** Fixed: N+1 queries in Settings, the Goals tab and the graph; a closed Vault's titles on an agent's graph; names that could be dicts; missing indexes. Today's counts went from 1.5 s to about 80 ms on the set 4 load.

## How to re-run each check

```
./tools/scan.sh                        # Frappe's semgrep rules over lifeos/ (or ./tools/scan.sh FILE...); exits 1 on any finding
python3 tools/scan_exceptions.py       # rewrite exceptions.md from the inline nosemgrep comments (--check to compare)
python3 scripts/http-methods.py        # rewrite the front end's list of GET methods after changing a decorator (--check to compare)
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench && bench --site lifeos.localhost run-tests --app lifeos'
node tools/acceptance.mjs              # ends with the scan (END.3); GETs are read-only on its site
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench && bench --site lifeos.localhost execute lifeos.loadtest.run_sources'
scripts/get-frappe-skills.sh           # the skills, pinned; then work through deep-app-audit and frappe-code-review as in audit.md and review.md
```

`tools/scan.sh` pins the rules to a commit, recorded in the script, and runs semgrep inside the `lifeos-bench` container, installing it there with pip if it is missing. The Mac needs only Docker.
