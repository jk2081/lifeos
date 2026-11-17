# Security audit: injection, XSS and client, auth and identity, files (S-B, S-C, S-D, S-E)

Applied by hand from Frappe's `deep-app-audit` skill (`security/_conventions.md`, `_framework-guards.md` and each scope file), on 17 November 2026, over `lifeos/`, `lifeos/api/`, `lifeos/ai/`, the DocTypes, `lifeos/www/` and `frontend/src`. Candidates were proved or refuted with Python on the bench (`lifeos.localhost`, as `family@lifeos.test`, rolled back) and with node for the Markdown renderer. No HTTP was sent.

| Check | Applied | Result |
| --- | --- | --- |
| S-B01 SQL injection | yes | No finding. Every interpolated piece of SQL is a fixed fragment or a meta-checked column; values are parameters (pre-step 6 step 2b). `permissions` builds its conditions with `frappe.db.escape`. |
| S-B02 Untyped ORM parameters | yes | **1 finding (High): `reset.undo`**. Scalar parameters are hinted `str`, so a dict or list is refused with 417 everywhere else. |
| S-B03 Query builder misuse | yes | No finding: the app does not use `frappe.qb` or `get_query`. |
| S-B04 Multi-statement and file primitives | yes | No finding: there is no injection point, and the MariaDB driver runs one statement. |
| S-B05 SSTI | yes | No finding: no user text is rendered as a template. `www/life.html` renders only `boot` (the CSRF token and the site name) through `tojson`. |
| S-B06 Jinja sandbox and globals | not applicable | Framework scope; the app adds no Jinja globals or filters. |
| S-B07 safe_exec | not applicable | Framework scope; the app uses no `safe_exec` or `safe_eval`. |
| S-B08 Command injection | yes | No finding: one `subprocess.run` (`sources._pdf_first_page`), with a list of arguments, no shell, and paths in a temporary folder it made. |
| S-B09 Dynamic dispatch | yes | No finding: `getattr(counts, kind)` in `ai/tools.py` checks `kind` against the fixed `COUNT_KINDS` set first; `devtools.LocalClient` is not whitelisted. |
| S-B10 Header, log, Redis, deserialisation | yes | No finding: no pickle, YAML or response headers; the Ask progress cache key is prefixed with the session user. |
| S-C01 Stored XSS in fields | yes | No finding: Vue templates escape; Desk escapes; server messages pass through `msgprint`'s sanitiser; `errorText` strips tags before a toast. |
| S-C02 Unsafe HTML sinks | yes | No finding: the two sinks (`Md.vue` `v-html`, the editor's `innerHTML`) render Markdown with raw HTML off and then DOMPurify. Proved in node: `<img onerror>`, `javascript:`, `vbscript:` and `data:` links, and a wiki link whose title and route carry quotes all came out escaped, before DOMPurify. |
| S-C03 Sanitiser bypasses | yes | No finding: the app uses DOMPurify and markdown-it as shipped, with extra forbidden tags. |
| S-C04 iframes, SVG, served HTML | yes | No finding: Life OS attachments must be private (`files.after_insert`), and Frappe serves `.svg` and `.html` as downloads (`FORCE_DOWNLOAD_EXTENSIONS`). |
| S-C05 CSRF | yes | No finding: every write is POST-only (pre-step 6 step 2a) and sends the CSRF token, including the `keepalive` save of a view and the logout. GETs are read-only (checked on the acceptance site by `lifeos_strict_get`). |
| S-D01 Session handling | yes | No finding: Frappe's sessions; `/life` sends a guest to login; logout is a POST. |
| S-D02 Password reset | not applicable | The app has no reset flow of its own. |
| S-D03 Two-factor | not applicable | Frappe's own. |
| S-D04 OAuth and SSO | not applicable | Only Frappe's Google Calendar integration, unchanged. |
| S-D05 Enumeration oracles | yes | No finding: record names are random hashes; a closed Vault document is answered as not found on purpose; `settings.find_users` is admin-only. |
| S-D06 HMAC and signed URLs | not applicable | None in the app. |
| S-D07 API keys and tokens | yes | No finding: agent keys are Frappe's; `devtools.agent_api_key` is not whitelisted; the AI key is a Password field, decrypted only server-side and never returned. |
| S-D08 Impersonation and set_user | yes | No finding: production code no longer switches users (pre-step 6 step 2d); demo and load-test code is not reachable over HTTP. |
| S-E01 Path traversal | yes | No finding: originals are read through `files.local_path` (pre-step 6 step 2e); the chat import checks read permission on the File first. |
| S-E02 Upload validation | yes | No finding in scope. Uploads use Frappe's `upload_file`; Life OS attachments are forced private. See the note on the export zip below. |
| S-E03 File privacy | yes | No finding: Frappe's File permission follows the attached record; `file_has_permission` closes Vault files to agents. |
| S-E04 Static file serving | yes | No finding: `public/` holds only the built front end and icons. |

## Confirmed findings

### S-B02-1. `reset.undo` writes proposals and inbox items it never checks (High)

- **File:** `lifeos/api/reset.py:322-328` (the `unaccept` branch of `undo`).
- **Entry point:** `POST /api/method/lifeos.api.reset.undo`. `log: str | list` is a list of operations sent by the client.
- **Actor:** any logged-in user who is not an agent. `_person()` checks only the login and the agent role, so this includes a family member, and any other user of a shared site.
- **Input:** `{"op": "unaccept", "proposal": <name or filter>, "item": <name or filter>}`.
- **Sink:** `frappe.db.set_value("Life Proposal", op["proposal"], {...status: "Pending"...})` and `frappe.db.set_value("Life Inbox Item", op["item"], {"status": "To Review", ...})`. No permission check runs, and a dict value is used as a filter.
- **Impact:**
  - The user resets proposals and inbox items in spaces they cannot read.
  - With `{"name": ["like", "%"]}`, they reset every proposal and every inbox item on the site. Accepted and rejected decisions go back to Pending, and the links to the records that were created are cleared.
  - `Life Proposal.validate` refuses such a status change even for the owner, outside `review.decide`; this path skips it.
- **Proof** (bench, rolled back; `family@lifeos.test` is a member of Shared only). An Accepted proposal and a Done item were made in Private.
  - The document layer refuses the family user write on both records.
  - After `reset.undo` as that user, the proposal was Pending and the item To Review.
  - With dict filters, To Review items went from 5 to 8 of 8, and Pending proposals to 12 of 12.
- **Fix:**
  - Accept only string names. Load the proposal with `permissions.get_doc_checked("Life Proposal", name, "write")`, and check that the item is that proposal's `inbox_item`, loaded the same way.
  - Better: make the undo log server-side, keyed by an opaque id, so the client cannot write the operations at all.
  - Check the `restore_deleted` and snapshot branches with the same rule. Today they are guarded by `trash.restore` (Write on the space) and by `get_doc_checked(..., "write")`.

## Refuted or uncertain candidates

- `reset.undo` `restore_deleted`: a filter in `op["doctype"]` or `op["name"]` only selects which Deleted Document to restore. `trash.restore` then requires Write on that record's space, so this is refuted.
- `reset.undo` and `someday.undo` snapshots: every record is loaded with `get_doc_checked(..., "write")` and saved through the document layer, so this is refuted. (Mass assignment of a snapshot is in fork 3's H01 scope.)
- `connections.touch`, `settings.reorder` and `views.save` `set_value`: the name comes from a scoped lookup or a write-checked document, so these are refuted.
- `journal.save_goal` `db.delete("Life Action Log", {"action_id": n})`: `n` comes from the saved goal's own rows, so this is refuted.
- `lifeos/www/life.html` Jinja: renders only server values through `tojson`, so this is refuted.
- **Outside this scope (K01):** `chat_import.conversations_from_zip` caps the zip at 1 GB on disk but not the size of `conversations.json` once decompressed. A person with Write access to a space could exhaust a worker's memory with a zip bomb. This needs Write access, and the worker is the site's own. Fork 3 decides.
