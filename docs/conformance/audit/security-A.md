# Security audit, area A (authorization)

Applied by hand from `deep-app-audit/security/A-authorization` (A01 to A14), with `_conventions.md` and `_framework-guards.md`, to `lifeos` at the pre-step 6 commits. Every candidate was traced from its whitelisted entry point to the sink and refuted where possible. Proofs ran as Python on `lifeos.localhost` as `owner@lifeos.test`, `family@lifeos.test` (a Life User who is a member of Shared only) and `hermes@lifeos.test` (a Life Agent in Private and Shared, both with the Vault switch off), creating `milkshake` records and rolling back.

| Check | Applied | Result |
| --- | --- | --- |
| S-A01 Whitelisted method authorization | yes: all 171 methods inventoried, checks traced one frame down | 1 finding (F2) |
| S-A02 IDOR / BOLA | yes: every name-taking method; the helpers `get_doc_checked`, `_thread`, `_row`, `_claimed_item`, `_cycle`, `_doc` | in F2 (the same cause) |
| S-A03 Client-settable permission bypass | yes: no `ignore_*` argument reaches a whitelisted signature; `**kwargs` only on `link_query`, unused | no finding |
| S-A04 Guest endpoints and rate limits | yes: no `allow_guest`; `/life` redirects a guest to login; Ask spends are capped monthly | no finding |
| S-A05 Role and permission model | yes: every DocType JSON read (permlevel 0 rows) | no finding; see note on Life Settings |
| S-A06 Permission query conditions and hooks | yes: every hook in `hooks.py`; each returns a condition or True/False on every path (`test_pre6_fixes` covers them) | 1 finding (F3) |
| S-A07 Child tables and linked fields | yes: list `fields`, `filters`, `order_by` and `summary` pass `utils.column` (DocType meta, no dot notation); Link fields are kept in the record's space by `org._check_links` | no finding |
| S-A08 Privilege escalation | yes: `settings.set_member`, `create_space`, `set_agent_vault`, `find_users` are Life Admin only; `validate_user_roles` keeps agents apart from people | no finding |
| S-A09 REST API parity | yes: `/api/resource` for every Life DocType as a Life User and a Life Agent | in F3 |
| S-A10 Realtime | yes: three `publish_realtime` calls, each to one `user` | no finding |
| S-A11 Share, assign, follow | yes: the app never shares or assigns; no Life DocType grants `share` | no finding |
| S-A12 Web form, portal, web view | not applicable beyond `www/life.py` (login required); no web forms, portal routes or `has_website_permission` | no finding |
| S-A13 Reports | not applicable: the app has no reports | no finding |
| S-A14 Controller methods that write behind a read check | not applicable: no controller method is whitelisted | no finding |

## Confirmed findings

### F1. `inbox.list` shows an agent the sources of Vault documents, with their full text (S-A06 / S-A01)

- **Severity: High.** A Life Agent reads records the owner closed to it.
- **Where:** `lifeos/api/inbox.py`, `list` (about line 257).
- **Path:** `GET /api/method/lifeos.api.inbox.list?space=Private&include_archived=1&summary={"fields":["transcript_md"]}` as the agent. `resolve_space` checks only membership. The WHERE has no Vault rule, unlike `claim_next`, `sources.list`, `timeline`, `archive.list` and `wiki.search`, which use `vault_guard` or `vault_hidden`. `summarise` groups by any column of the DocType, so `transcript_md` (and `summary_md`) come back as group values. Without `summary`, the rows give title, instruction, error, area and owner.
- **Proof:** an inbox item in Private with `vault_document` set and transcript "milkshake SECRET passport text 9988". As the agent: `frappe.has_permission` returns False, and `frappe.get_list("Life Inbox Item")` returns `[]`, but `inbox.list(...)` listed the item, and `inbox.list(..., summary={"fields": ["transcript_md"]})` returned `[{'transcript_md': 'milkshake SECRET passport text 9988'}]`.
- **Fix:** when `permissions.vault_hidden(space)`, add `ifnull(i.vault_document, '') = ''` to `where` before the tab counts, the summary, the rows, the totals and `pending_total`. Add a test that runs as the agent.

### F2. `reset.undo` resets any proposal and any inbox item by name, in any space (S-A01 / S-A02)

- **Severity: Moderate.** A Life User writes records in a space they do not belong to. It needs the record names, which are random hashes the user cannot list.
- **Where:** `lifeos/api/reset.py`, `undo`, the `unaccept` branch (about lines 322 to 328).
- **Path:** `POST /api/method/lifeos.api.reset.undo` with `log=[{"op": "unaccept", "proposal": "<P>", "item": "<I>"}]`. `_person()` only refuses agents. `frappe.db.set_value("Life Proposal", op["proposal"], {status: Pending, decided_by: None, ...})` and `frappe.db.set_value("Life Inbox Item", op["item"], {status: "To Review"})` bypass the document layer, and nothing checks either record. The delete of the created record in the same branch is checked.
- **Proof:** as `family@lifeos.test` (spaces: Shared), on an Accepted proposal and a Done item in Private (`has_permission` read False): `undo` returned ok. Afterwards the proposal was `('Pending', None)` and the item `To Review`.
- **Fix:** load the proposal with `permissions.get_doc_checked("Life Proposal", op["proposal"], "write")`. Take the item from `prop.inbox_item` (not from the log), and check it with `get_doc_checked(..., "write")`. Then write.

### F3. Proposals and links of a closed Vault stay readable to agents through REST and MCP (S-A06 / S-A09)

- **Severity: Low.** The proposals are usually the agent's own work. They also carry any edits the owner made before accepting.
- **Where:** `lifeos/permissions.py`, `query_conditions` and `has_permission` for `Life Proposal` and `Life Link`. They apply the space only. The Vault rule covers `Life Vault Document`, `Life Index` and `Life Inbox Item`.
- **Proof:** as the agent, with Private's Vault closed: `frappe.get_list("Life Proposal", filters={"inbox_item": <vault-locked item>}, fields=["preview","payload"])` returned the "Vault Document" proposal with `{"title":"milkshake passport","number_last4":"9988"}`. `frappe.get_list("Life Link", filters={"to_name": <vault doc>})` returned the link and its text.
- **Fix:** for agents in closed spaces, leave out proposals whose inbox item has a `vault_document`, or whose kind is "Vault Document", and links from or to a Vault document. Apply this in both the query condition and `has_permission`.

## Refuted or uncertain

- `chats.close_item`, `inbox.submit_result`, `fail_item`, `tasks.carry_forward`, `journal.tick`, `toggle_habit`, `carry_month_goal`, `archive.set` and `restore` have no visible check at the wrapper. Each is checked one frame down (`_row`, `_claimed_item`, `journal.carry_task`, `set_tick`, `set_archived`: `check_permission("write")`).
- `trash.restore` inserts with `ignore_permissions`. The space of the deleted record is checked first with `require_space(write=True)`. Agents are refused.
- `calendar.add_event` and `delete_event` use `ignore_permissions`. The space check comes first, and agents cannot delete.
- `someday.undo` and `reset.undo` (snapshot branch) take a client-chosen doctype. `get_doc_checked(..., "write")` and `save()` check it with the framework's own permission.
- `wiki.change` and `wiki.undo` load a `Life Wiki Change` without a check, then check the page it belongs to.
- `ask.run_action` and `insights.act` run actions written by the model. Each action goes through checked methods as the person.
- `proposals.apply` copies a file only when it is one of the inbox item's own files.
- `Life Settings` is readable by Life User and Life Agent through `/api/resource`. The API key is a Password field (not returned), and `settings.get` shows the same values to members anyway. This is tenant configuration that is already exposed, so it is not a finding.
- `archive.archive_project` archives every record of a project, Vault documents included, for a user with write access to the project. An agent with the Vault closed can archive Vault documents it cannot read. This is reversible and in the agent's own space, so it is noted, not a finding.
- **Uncertain, for scope E:** `connections.start_import` checks `read` on the first `File` row with the given `file_url`, and the job then reads by `file_url`. Whether a user can make a File row that points at someone else's private `file_url` is a File question, so it is left to the files-and-paths scope.
