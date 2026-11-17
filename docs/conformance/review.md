# Code review against `frappe-code-review` (pre-step 6, step 4)

Scope: `lifeos/` (API, AI, DocType controllers, hooks, patches), `agent/fake_agent.py`, and the front end's server-call layer (`frontend/src/lib/api.js`, `ask.js`, `views.js`). Reviewed on 17 November 2026, after steps 2 and 3. The audit's findings (`audit.md`) are not repeated here.

Each finding is **REAL**, meaning it breaks something for someone, or **STYLE**. Query counts and times were measured on `lifeos.localhost` with the load-test data present (52 spaces, 122,045 index rows), inside a rolled-back session.

## 1. Correctness and stability

Checked:

- **Partial commits:** none left in request paths after step 2c.
- **Destructive calls with empty filters:** every `frappe.db.delete` has a non-empty filter, and the `in` lists are guarded with `or [""]`.
- **Date comparisons:** dates are compared as dates (`getdate`) throughout `someday`, `journal` and `counts`.
- **Return shapes:** `get_value` results are checked before use in the paths read.
- **Long-standing semantics:** unchanged, apart from what DECISIONS lists for pre-step 6.

No REAL finding.

- **R1.1 STYLE.** Assertions for internal invariants are rare. The code throws user-facing errors instead (for example "Week must be 1 to 12"). That is right for input; nothing stateful needs an `assert` here (no ledgers).

## 2. Security

Checked:

- **SQL:** after step 2b, no caller value reaches SQL unparameterised.
- **Type confusion at whitelisted boundaries:** every parameter now has a type hint that Frappe validates. Names are `str`, so `{"name": [...]}` filters are refused at the boundary.
- **Other checks:** no `eval`/`exec`, no `allow_guest`, and secrets live in a Password field (`Life Settings.anthropic_api_key`). File paths go through `files.local_path` (step 2e). The front end escapes Markdown and runs DOMPurify (audit S-C).

Findings:

- **R2.1 REAL (low), hardening.** `reset.apply_batch` (`lifeos/api/reset.py:245-272`) reads `doctype` and `name` from each element of the `items` list. Hints validate only the outer list, so a dict as `name` becomes a filter in `frappe.db.exists`, `get_value` and `get_doc_checked`. Every action still checks permission on the record it loads, so a user cannot reach a record they could not name. But the record acted on is "the first match", not the one named. The same pattern applies to the snapshot ops in `reset.undo` (`someday.restore_snapshot`, `lifeos/api/someday.py:281`).
  - **Fix (small, safe):** `if not isinstance(name, str): continue` in `apply_batch`, and `isinstance(snap.get("doctype"), str) and isinstance(snap.get("name"), str)` in `restore_snapshot`.
- **R2.2 STYLE.** There are 61 `ignore_permissions=True` writes (counted by the audit's P02). Each one read is preceded by `get_doc_checked` or `require_space`. They are worth keeping in mind when a new path is added.

## 3. Performance

Checked: the request paths of every GET method for database calls in loops (an AST scan of `lifeos/`, then the read endpoints measured), unindexed filters on large tables, and aggregation in SQL. The slow Today counts (count doors calling whole list methods) are being fixed separately and are left out here.

Findings:

- **R3.1 REAL (moderate). `settings.get` is N+1 over spaces and members** (`lifeos/api/settings.py:91-100`, `_member_rows` at `:52-55`).
  - **Measured:** 515 queries and 157 ms for the owner, with 52 spaces and 168 members. That is one `get_doc` per space, plus `get_fullname`, a `User.user_image` lookup and `is_agent` (roles) per member.
  - **Effect:** for a Life Admin it grows with every space on the site.
  - **Fix (small, safe):** load members for all spaces with one `get_all("Life Space Member", filters={"parent": ("in", names)})`. Get names and images with one `get_all("User", ...)`, and roles with one `get_all("Has Role", ...)`.
- **R3.2 REAL (moderate). `journal.goals` is N+1 per goal** (`lifeos/api/journal.py:114-129`).
  - **Per goal:** up to five `get_value` calls (`carried_into`, the project title, the carried-from goal's cycle and its title, the carried-into cycle's title), on top of one `grid()` per cycle.
  - **Measured:** 34 queries for 9 goals in 2 cycles. A 12 Week Year makes four cycles a year, so after a few years the Goals tab runs hundreds of queries.
  - **Fix (small):** collect the names, then one `names_map` per DocType and one `get_all("Life Goal", filters={"carried_from": ("in", names)})`.
- **R3.3 REAL (low to moderate). `graph.get` runs `exists` and `title_of` per link** (`lifeos/api/graph.py:49-64`). It reads up to 2,000 `Life Link` rows per space, and for each endpoint not already a node it calls `frappe.db.exists` and `rules.title_of`. At the 2,000 cap that is up to about 4,000 more queries in one request. Goals also do `exists` and `get_value` per project.
  - **Fix:** group the unknown endpoints by DocType, then one `get_all(dt, filters={"name": ("in", names)}, fields=["name", title_field])` per DocType.
- **R3.4 REAL (low). Agent "last filed" scans unindexed `owner` columns** (`lifeos/api/settings.py:70-71`). `select max(creation) from tabLife Proposal / tabLife Chat Log where owner=%s` runs once per agent on every Settings load. `owner` has no index on either table, and chat logs reach tens of thousands after an export import.
  - **Fix:** an index on (`owner`, `creation`) in `index.ensure_indexes`, or `order by creation desc limit 1` over an indexed column.
- **R3.5 REAL (low). Today's "goals with no tasks" checks `exists` per goal, with `Life Task.goal` unindexed** (`lifeos/counts.py:127`).
  - **Fix:** one `select distinct goal from tabLife Task where space=%s and goal in %s`, and `search_index` on `Life Task.goal`. This sits beside the Today fix and is small.
- **R3.6 STYLE.** `Life Proposal.created_doctype/created_name` and `Life Ask Thread.scope_doctype/scope_name` are unindexed Dynamic Links. Frappe scans them on every delete of a linkable record, even though they are now in `ignore_links_on_delete`, because the check filters after the query. Deletes are rare, so this is not worth a schema change now.

## 4. Concurrency

Checked:

- **Check-then-insert:** habit ticks, action logs, external IDs and connections all have unique indexes (`index.ensure_indexes`). `claim_next` locks with `for update skip locked`. Month plans have deterministic names, so a duplicate insert fails rather than forking.
- **Wiki and note saves:** these compare `base_version`, and Frappe's `check_if_latest` (`select … for update` on `modified`) refuses the second of two simultaneous saves.
- **Query-building state:** stateless.

Findings:

- **R4.1 = audit Q-B05** (`views.save` check-then-insert). Confirmed, not repeated.
- **R4.2 STYLE.** Per-request caches are kept by hand in `frappe.local` (`permissions.user_spaces`, `vault_open_spaces`; `lifeos/permissions.py:8-30, 92-96`), which the skill advises against. They are request-scoped, and `permissions.clear_cache()` is called after membership changes, so they work. `@frappe.request_cache` would say the same with less code.

## 5. Readability and maintainability

- **R5.1 STYLE.** Several files are well over the `code-style` 300-line guide:
  - `lifeos/api/wiki.py` (~560 lines)
  - `lifeos/api/journal.py` (~520)
  - `lifeos/journal.py` (~480)
  - `lifeos/proposals.py` (~430)
  - `lifeos/ai/tools.py` (~410)

  Each is one responsibility, so splitting would be churn without a defect.
- **R5.2 STYLE.** Some signatures run to about 170 characters, for example `tasks.list` and `goals.list` since the type hints. They are readable but long. Wrapping them would be a no-op change.
- **R5.3 STYLE.** Imports inside functions (`from lifeos.api import …`) are common. They avoid import cycles between `lifeos.api.*` and the core modules, and are kept.
- **R5.4 STYLE.** `frappe.flags.lifeos_*` switches (`lifeos_app_write`, `lifeos_wiki_api`, `lifeos_making_preview`) are set and reset in `try/finally` everywhere they are used. They were checked: none leaks.

## 6. API design and backward compatibility

- **R6.1 STYLE (recorded).** Pre-step 6 made every read GET-only and every change POST-only. For REST clients that sent reads as POST, this is a breaking change. It is recorded in DECISIONS and `agent/SKILL.md`; MCP is unaffected.
- **R6.2 STYLE.** Loose parameters that take several disjoint types remain, deliberately: `str | list | dict` for `filters`, `summary` and `payload`, because GET sends JSON text while MCP sends objects. Each is parsed once at the top of the method.
- **R6.3 STYLE.** Two tests were changed in this set, each justified in DECISIONS:
  - `test_ux2_views.test_what_is_saved` accepts `FrappeTypeError` as well.
  - None of the existing assertions on deletion were bent; new tests were added instead.

## 7. Testing

Checked: the pre-step 6 fixes each have a regression test (`test_pre6_fixes.py`, `test_pre6_conventions.py`, 21 + 2 tests).

- **R7.1 STYLE.** About 110 test lines use `today()` with no frozen clock. Week- and month-boundary logic (Today's This week, the weekly review, habits) could flake when a run crosses midnight, or on the last day of a month. No failure has been seen. Prefer `freeze_time` in new date-heavy tests.
- **R7.2 STYLE.** `tests/base.py` and `test_m8_search_graph.py` call `frappe.db.commit()`. The reason is noted inline: MariaDB's FULLTEXT index sees rows only after commit. `tearDownClass` purges the test spaces.
- **R7.3 STYLE.** `test_pre6_fixes.TestChatImportSavepoints` patches `chats.log` to inject one failure. A real failing conversation is hard to build from an export, and that is the only mock in the new tests.

## 8. Error messages, logging and observability

Checked: messages name the record or field (`{0} looks like it holds a full number…`, `{0} is still used by other records…`). Background failures are logged with titles (`Life OS chat import: one conversation failed`, `Life OS insights for <space>`, `Life OS Ask failed`). Tracebacks are kept by `log_error`, and no secret appears in a message or log.

- **R8.1 = audit Q-B40** (`ai/client.api_key` swallows a decryption error without a log). Confirmed, not repeated.
- **R8.2 STYLE.** A few messages are generic: "Unknown status.", "Unknown action.", "No such action." (`lifeos/journal.py:175`, `lifeos/api/ask.py:228, 249`). Naming the value received ("Unknown status Foo; use Open, Done or Dropped") would make them searchable.
- **R8.3 STYLE.** `calendar.google_status` (`lifeos/api/calendar.py:21`) catches every exception to mean "not connected", with no log. That is acceptable for a status badge, but a broken Google setup stays invisible.

## Summary of REAL findings, by consequence, and what was done

| Finding | Done |
| --- | --- |
| Today's counts took 1.5 s on the set 4 load (found while re-running the load test; Notes and Inbox counts scanned whole tables, and every task count ran the full task list) | **Fixed.** Two composite indexes (`life_index_notes`, `life_inbox_space_state`), and `tasks.total`, which counts with the same WHERE as `tasks.list` without fetching rows. Today: 1,537 ms to about 90 ms. |
| R3.1 `settings.get` N+1 over spaces and members (moderate) | **Fixed.** Spaces, members, users and roles are read in five queries, whatever the number of spaces. |
| R3.2 `journal.goals` N+1 per goal (moderate) | **Fixed.** `_goal_links` reads projects and carried-from/into cycles in four queries. |
| R3.3 `graph.get` per-link `exists` and title (low to moderate) | **Fixed.** One query per DocType (`titles`). The same pass found that a link to a Vault document put its title on an agent's graph while the Vault was closed; that is fixed too. |
| R2.1 `reset.apply_batch` / `restore_snapshot` accept a dict as a record name (low; hardening) | **Fixed.** Names must be strings. |
| R3.4 agent "last filed" over unindexed `owner` (low) | **Fixed.** Indexes on (`owner`, `creation`) of Life Proposal and Life Chat Log. |
| R3.5 Today's "goals with no tasks" per-goal `exists`, `Life Task.goal` unindexed (low) | **Fixed.** One query for the ticked goals; index on (`goal`, `status`) of Life Task. |

The new indexes are added by `index.ensure_indexes` on install and by the patch `v6.conformance_indexes` on existing sites. The STYLE points above are left as they are: they do not break anything, and changing working code for style alone is not this set's job.

## The set's own diff

Before closing the set, its whole diff (`eef9700..HEAD`) was reviewed again against the skill by a fresh reviewer. It found two defects, both fixed:

- The first fix for Q-B26 used `ignore_links_on_delete`, which frees *every* link of a DocType. A project or area that an idea or insight is filed under could then be deleted, and the idea could no longer be saved. The fix now clears only the bookkeeping pointers in `org.on_trash`.
- The graph still showed an agent a closed Vault document when that document was the graph's centre. Fixed.

Its style notes, not acted on: long signatures since the hints (`wiki.pages`, `sources.list`, `chats.list`, `goals.create`); repeated `nosemgrep` reasons on consecutive lines; `ask.ask` catches every exception, so after a deadlock `msg.reload()` can still end in a 500; and `wiki.health`'s `vault_hidden` branch copies the data without filtering it (older than this set).
