# Deep audit: quality track (correctness rules and K02)

Pre-step 6, step 3. The `deep-app-audit` script could not run here: the bench lives inside the `lifeos-bench`
container, and the script's agents run on the host with a tool allowlist (`bench --site`, file reads) that cannot reach
it. The checklists in `.claude/skills/deep-app-audit/quality/` were applied by hand to the code at commit `e73d7f0` plus
the pre-step 6 changes in the working tree, following `quality/_conventions.md`. Every candidate was re-read and, where
practical, shown on `lifeos.localhost` with a Python session that rolled back (marked `milkshake`). Nothing was committed
to the site.

## Rules applied

| Id | Applied | Result |
| --- | --- | --- |
| Q-A01 to Q-A41, Q-K01 | Not applicable | They are about overriding or customising ERPNext and core DocTypes. Life OS has its own DocTypes, overrides no core class or whitelisted method, and ships no Property Setters or Custom Fields except the one `Event.life_space` field. |
| Q-B01 transaction control in lifecycle | Yes | No commit or rollback in any controller or `doc_events` handler. The remaining commits are in `after_install`, the chat import worker job and the load test; rollbacks are to savepoints. |
| Q-B02 own the rollback you catch | Yes | Clean. Every `except` around a write either re-raises, throws, or rolls back to a savepoint (`review.decide_all`, chat import, nightly insights). |
| Q-B03 DDL ends the transaction | Yes | Clean. `index.ensure_indexes` uses `add_index`/`sql_ddl`, which commit first by design, in install, migrate and the v4 patch; the v4 patch's writes before it are re-runnable. |
| Q-B04 enqueue after commit | Yes | Clean. The one enqueue (`connections.start_import`) passes every value it needs; the file was committed by its upload request and the progress lives in the cache. |
| Q-B05 check then insert | Yes | Clean where it matters: habit logs, action logs, external IDs and connections carry unique indexes (`index.ensure_indexes`); month plans and logs have deterministic names. Life View State: see Q-B05 finding below. |
| Q-B06 lock the rows you change | Yes | Clean. Edits that depend on what was read go through `doc.save()`, whose `check_if_latest` locks the row (`FOR UPDATE`) and refuses a stale save; `claim_next` uses `for update skip locked`. |
| Q-B07 fixed lock order | Yes | Clean. One explicit lock in the app (`claim_next`). |
| Q-B08 idempotent endpoint and job | Yes | Clean. `submit_result` needs the item in Processing and a concurrent duplicate fails the item's timestamp check and rolls back; imports dedupe on the unique external ID; scheduler jobs are state-driven. |
| Q-B09 computed field from itself | Yes | Clean. `last_touched_on` and `last_activity_on` are touch stamps by design. |
| Q-B10 rebuild a child table | Yes | Clean. `also_in`, note sources and month plan habits are rebuilt, not appended on save. |
| Q-B11 patch re-runnable | Yes | Clean. Every patch writes conditionally (`where ... is null`, `ifnull`) or idempotently. |
| Q-B12 reload before a patch reads | Yes | Clean. All patches are `post_model_sync`. |
| Q-B13 schema change needs a data patch | Yes | Clean. The one mandatory field added to an existing DocType since set 2 (`Life Goal.goal_type`) shipped with `v3.goal_type_for_existing_goals`; the rest are new DocTypes. |
| Q-B16 every read may be empty | Yes | Clean. Multi-field reads are guarded or follow link fields the framework keeps intact. |
| Q-B17 coerce at the boundary | Yes | Clean after pre-step 6: every whitelisted argument is type-hinted and coerced by Frappe. |
| Q-B18 money at precision | Not applicable | No money or quantity comparisons (AI cost is reported, not compared at precision). |
| Q-B19 dates as dates | Yes | Clean. No `NOW()`/`CURDATE()` in SQL; comparisons are date with date or datetime with datetime. |
| Q-B20 single DocType API | Yes | Clean. `get_single_value`, `set_single_value` and `get_cached_doc` only. |
| Q-B21 destructive call filter | Yes | Clean. Every delete filters on a saved record's name; `index.rebuild` clears the index on purpose. |
| Q-B25 one owner writes status | Not applicable | Every status field is on a DocType the app owns end to end. |
| Q-B26 dependents on delete | Yes | **Finding** (High): bookkeeping Dynamic Links block deleting records. Index rows and links are removed in `org.on_trash`. |
| Q-B27 child row through parent | Yes | Clean. The one direct child write (`Life Goal Action.ticks`) is a bookkeeping total no parent computation reads. |
| Q-B28 ORM bypass | Yes | **Finding** (Moderate): status written with `set_value` leaves the index stale. |
| Q-B29 change after the write step | Yes | Clean. Post-write hooks use `set_value`/`db_set`, or write through `archive_project`. |
| Q-B31 request state in lifecycle | Yes | Clean. Scheduled jobs do not depend on the session user (nightly insights pass the owner; claims and health need none). |
| Q-B32 handler order | Yes | Clean. One app; controller methods run before `org.*` handlers, which read only what is saved. |
| Q-B33 lifecycle names | Yes | Clean. Every controller and `doc_events` method name is one the framework calls. |
| Q-B34 update after submit | Not applicable | No submittable DocType, no `allow_on_submit`. |
| Q-B35 validate in every path | Yes | Clean. ORM bypasses write what `validate` would (for example claims cleared together with status New). |
| Q-B36 filter by docstatus | Not applicable | No submittable DocType. |
| Q-B37 ordered queries tie-breaker | Yes | Uncertain only (see below). |
| Q-B40 optional step must not fail | Yes | **Finding** (Low): the AI key read swallows errors without a log. |
| Q-B42 templates with missing data | Not applicable | No print formats, email templates or Jinja pages beyond the SPA shell `www/life.html`. |
| Q-B43 cache after raw write | Yes | Clean. Raw SQL writes never touch DocTypes read through `get_cached_doc` (Life Settings, Life Cycle). |
| Q-B44 site state at module scope | Yes | Clean. No module-level site state; the Vault cache lives in `frappe.local`. |
| Q-B45 refresh the field | Not applicable | No desk form scripts; the front end is a Vue app. |
| Q-K02 framework surface breakage | Yes (reduced) | Clean. See the check table below. |

## Confirmed findings

### [HIGH] Records that a proposal, an insight, an Ask thread or an idea points to can never be deleted

- **Id:** `Q-B26`
- **File:** `lifeos/trash.py:27-31` (refusal), caused by the Dynamic Link fields `Life Proposal.created_name`, `Life Insight Evidence.ref_name`, `Life Ask Thread.scope_name`, `Life Idea.brought_to_name` / `source_name`, `Life Wiki Change.source_name`
- **Trigger:** the owner deletes (record pane, the trash, Reset's Delete batch or one-by-one D) a task, note or source that was accepted from an inbox proposal, cited by any insight (Dismissed ones included), used as the scope of an Ask question, or brought back from Someday.
- **Failure:** Frappe's delete check finds the bookkeeping Dynamic Link and refuses: "X is still used by other records, so it cannot be deleted. Archive it instead." A Reset Delete batch stops at the first such item and nothing in the batch is deleted.
- **Impact:** every record made through inbox review, which is the main way records are made, and every stuck task the nightly Stuck insight cites, which are exactly Reset's candidates. The person cannot see or remove these pointers, so the record can never be deleted.
- **Proof:** `trash.delete` → `frappe.delete_doc` → `check_if_doc_is_dynamically_linked` → `LinkExistsError`, caught and re-thrown in `trash.py:30`. `reset.apply_batch` (`reset.py:247`) does not catch it.
- **Evidence:** on `lifeos.localhost`, rolled back: a task accepted with `review.decide` → `trash.delete` refused; a task used as an Ask thread's scope → refused; a task cited by a Dismissed insight → refused; `reset.apply_batch("delete", [a, b])` with only `b` cited → "milkshake b is still used by other records", nothing deleted.
- **Suggested fix:** list the bookkeeping DocTypes in `ignore_links_on_delete` in `hooks.py` (`Life Proposal`, `Life Insight`, `Life Ask Thread`, `Life Idea`, `Life Wiki Change`; check the child tables), and let readers treat a missing target as gone (insights already drop missing evidence). Keep the refusal for real references such as a task's project. Add a test that a task made from a proposal can be deleted and restored.

### [MODERATE] Inbox item status written with `set_value` leaves the Life Index row stale

- **Id:** `Q-B28`
- **File:** `lifeos/api/reset.py:328` (`undo`, op `unaccept`); also `lifeos/api/inbox.py:87` (`release_stale_claims`)
- **Trigger:** in Reset, accept the pending notes of an item (`accept_notes` batch) and click Undo; or an agent's claim lapses and the five-minute job puts the item back to New.
- **Failure:** `frappe.db.set_value("Life Inbox Item", ..., {"status": "To Review"})` updates the item but not its index row, which `index.update` keeps only on save. Sources reads the index status: the item is To Review again, but Sources' In Inbox filter (`sources.STATUSES["inbox"]`) does not list it, and its row still shows Done. A lapsed claim keeps showing Processing.
- **Impact:** the owner, until the item is saved again; an item put back for review is hard to find from Sources.
- **Proof:** `reset.undo` → `set_value` with no `index.update`; compare `inbox._finish_if_decided`, which calls `index.update(doc)` after the same kind of write.
- **Evidence:** on `lifeos.localhost`, rolled back: after `_accept_notes` the item was Done and the index Done; after `reset.undo(log)` the item was To Review, the index still Done, and `sources.list(status="inbox")` did not include it.
- **Suggested fix:** call `index.update(frappe.get_doc("Life Inbox Item", name))` after both writes, or save the item through the ORM.

### [MODERATE] A saved list view can stop being remembered after two first saves race

- **Id:** `Q-B05`
- **File:** `lifeos/api/views.py:52-56` (`save`)
- **Trigger:** two `views.save` calls for the same screen and space, with no saved state yet, overlap: the debounced save in `frontend/src/lib/views.js` fires again while the first request is still running (over a second), or two tabs or devices save the same screen.
- **Failure:** both see no row and both insert, because nothing makes (user, screen, space) unique. From then on `save` updates the newest row (`get_value`'s default order, creation desc), while `get_all` builds its map in the same order and lets the oldest row win. The screen loads the stale state forever.
- **Impact:** the owner or a family member: a filter, sort or column change on that screen is never remembered across reloads or devices.
- **Proof:** `views.save` check-then-insert with `autoname: hash` and no unique index; `get_all` loops `frappe.get_all(...)` into a dict, so the last row read wins.
- **Evidence:** on `lifeos.localhost`, rolled back: two rows for one screen → `get_all` returned the older state; after `views.save(..., {"v": "latest"})` it still returned the older state.
- **Suggested fix:** name the row from (user, screen, space) so a second insert fails and is retried as an update, or add a unique index on those columns; delete duplicates in a patch.

### [LOW] The AI key read hides decryption errors

- **Id:** `Q-B40`
- **File:** `lifeos/ai/client.py:50-55` (`api_key`)
- **Trigger:** the stored key cannot be decrypted, for example after a backup is restored on a site with another `encryption_key`.
- **Failure:** `except Exception: key = None` with no log; Ask and the AI insights say "Ask is not set up yet" while Settings shows a key is stored.
- **Impact:** the owner and whoever debugs it; nothing in the Error Log says why.
- **Proof:** `get_decrypted_password(..., raise_exception=False)` already returns None for a missing key, so the `except` only catches real failures.
- **Evidence:** not executed.
- **Suggested fix:** log the exception (`frappe.log_error(title="Life OS AI key could not be read")`) before returning None.

## Refuted or uncertain candidates

- Q-B06 wiki and notes edited from two places at once: refuted; `doc.save()` locks and compares `modified` (`check_if_latest`), so the second save fails, and both editors also send `base_version`.
- Q-B03 v4 patch writes before `ensure_indexes`: refuted as a failure; the early commit happens, but every write in the patch is re-runnable.
- Q-B05 one active cycle per space, one rules page per space, area names: validate-only checks that two concurrent saves could pass; no realistic trigger for one owner, so not reported.
- Q-B37 Timeline and Sources order by `record_date desc, modified desc`, and `index._write` gives every row of a batch the same `modified` (44 of 65 index rows on `lifeos.localhost` tie): uncertain. Paging Timeline and Sources at page sizes 3 to 10 returned every row exactly once, so no failure was seen. Adding `ref_name` as a last sort key would remove the doubt.
- Q-B28 `files.after_insert` and `sources.on_file_attached` write with `set_value`: refuted; the preview field is not indexed, and `on_file_attached` calls `index.update` itself.
- `api/calendar.google_status` catches every error with no log: not reported; a read of an optional integration's status.

## Q-K02: framework surface (reduced pass)

Run in the bench against Frappe 16.56.0: every `from frappe... import` (19), every `frappe.<attr>` chain (50 roots), and every
`frappe.db.<method>` the app uses (21) resolved at run time; none is removed, and none is in `deprecation_dumpster.py` (36 rows).
The callables with a parameter deprecation that the app calls (`enqueue`, `Database.set_value`, `generate_hash`, `connect`)
are not called with the deprecated parameter (`job_name`, `is_async=False`, a `None` name, `txt`). All 28 dotted values in
`hooks.py` resolve; every hook key is read by core or is app metadata. All 145 front-end call targets resolve and are
whitelisted. No `doc_events` commit, no override class, no monkey patch, no assignment to a `frappe.local` proxy.
Not done: dating findings against core's git history (there were none) and the full reachability closure.

Coverage: every Python module of `lifeos/` except tests, demo, loadtest and devtools (development tools); DocType JSON;
patches; hooks. Not searched on purpose: the A-customization rules and K01. Unresolved: none.
