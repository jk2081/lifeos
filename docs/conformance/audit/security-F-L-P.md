# Security audit: scopes F to L and posture checks P01 to P05

Pre-step 6, step 3. The checklists of Frappe's `deep-app-audit` skill were applied by hand: its script could not run here, because the bench is inside Docker and the script's agents cannot reach it. The conventions in `security/_conventions.md` and `security/_framework-guards.md` were followed. Every candidate was re-read from entry point to sink and, where useful, proved with Python on the bench (`lifeos.localhost`, records marked `milkshake`, rolled back, never committed). Actors: the owner (`Life Admin`, `Life User`), a family member (`Life User`, Shared space only) and an agent (`Life Agent`, Private and Shared, Vault switch off).

## Checks applied

| Id | Applied | Result |
| --- | --- | --- |
| S-F01 SSRF and TLS | yes | No finding. The app's only outbound call is the Anthropic SDK (`lifeos/ai/client.py`), at a fixed host, with TLS verified by the SDK. No URL from a request is fetched; `source_url` is only stored and opened in the browser. No `verify=False`. |
| S-F02 header trust | yes | No finding. No `get_url`, `request.host`, forwarded header or IP control in the app. |
| S-F03 open redirect | yes | No finding. `www/life.py` redirects to `/login?redirect-to=<request path>` (always a path on the site). Front-end links pass `safeUrl`/an `https?:` check, and Gmail links match a fixed pattern (`DigestView.vue`). |
| S-G01 secret storage | yes | No finding. The one secret, `Life Settings.anthropic_api_key`, is a Password field; `settings.set_ai_key` is owner-only and never returns it; `settings.get` returns `key_set` only. No secret in git history (the one `sk-ant-` hit is an input placeholder). `docker/docker-compose.yml` holds the local-only MariaDB root password of the throwaway stack (deployment, informational). |
| S-G02 secrets in logs and responses | yes | No finding. `session.boot` holds no secret; `log_error` calls log tracebacks, not settings; the AI client's errors carry the API's message, not the key. |
| S-G03 weak randomness | yes | No finding. `random` only in the load test; `generate_hash(15)` only for the development agent key in `devtools.py`; `fake.py` ids are test data. |
| S-G04 crypto primitives | yes | No finding. SHA-1 is used only for index row names and insight fingerprints (identifiers, not security). No own encryption. |
| S-H01 mass assignment | yes | No finding. `tasks.update` and the other write methods take an allowlist of fields; `org.validate_common` refuses links to records of another space on every space DocType and on child rows. |
| S-H02 workflow and status bypass | yes | No finding. No submittable DocTypes; status changes go through `doc.save()` after `get_doc_checked(..., "write")`. |
| S-H03 financial validation | not applicable | No money, prices or payments. AI spend is computed on the server from token counts. |
| S-H04 race conditions | yes | No finding at this bar. External ids are checked before insert (`sources.check_external_id`); a duplicate under a race would be a duplicate chat or item of the same user, not a boundary crossing (left to the quality review, `Q-B05`). |
| S-H05 tenant scoping (Life Space) | yes | One finding (below, with S-I01). Every whitelisted method that takes `space` resolves it through `permissions.resolve_space` or loads records through `get_doc_checked`. |
| S-I01 over-fetching endpoints | yes | **One finding: the trash lists Vault documents to agents.** |
| S-I02 metadata leaks | yes | No finding. No guest endpoints; errors are Frappe's standard responses. |
| S-I03 search leaks | yes | No finding. `search.query`, `links.*`, `graph.get`, `timeline.get`, `area.get`, `archive.list`, `sources.list` and the `Life Index` lists apply `vault_guard`; `link_query` uses `frappe.get_list` (permission query conditions). |
| S-I04 PII | yes | No finding. `settings.find_users` is owner-only; `settings.get` lists members of the caller's own spaces only. Vault numbers are refused unless only the last four characters are kept. |
| S-J01 recipient control | not applicable | The app sends no email or SMS. |
| S-J02 inbound email trust | not applicable | No inbound email handling; agents file email digests through the API as themselves. |
| S-J03 Communication permission | not applicable | No Communication use; `add_comment` writes fixed text on an inbox item the caller already wrote. |
| S-K01 resource exhaustion | yes | **Two Low findings**: the quick-add date pattern and the chat export's uncompressed size. List methods clamp `page_length` to 100; Pillow's decompression-bomb guard applies to previews and thumbnails. |
| S-K02 job abuse | yes | No finding. The only enqueue is the chat import: people with Write access only, one per space and system at a time, and the job runs as that person. |
| S-L01 Python dependencies | yes | No finding for the app. `pip-audit` on the bench's environment: `gitpython 3.1.62` (6 CVEs, fixed in 3.2.x) and `pdfkit 1.0.0` (PYSEC-2026-2860), both Frappe's dependencies; Life OS uses neither. The app's own dependency, `anthropic==2.9.0`, has no known advisory. |
| S-L02 JS dependencies | yes | No finding. `yarn audit` on `frontend/yarn.lock`: one moderate advisory, `postcss-selector-parser 6.0.10` (quadratic selector parsing) through `frappe-ui > @tailwindcss/typography`. It runs at build time only, on the app's own CSS. Dev dependencies: none. |
| S-P01 endpoint hardening coverage | yes | Table below. |
| S-P02 invariant diffs | yes | Table below. |
| S-P03 security headers | yes | Table below. |
| S-P04 dependency pinning | yes | List below. |
| S-P05 CI/CD and repo hygiene | partly | No `.github/` and no CI in the repo; the hosting organisation was not reachable. History scanned for secrets (none). |

## Confirmed findings

### [MODERATE] The trash lists deleted Vault documents to an agent while the Vault switch is off

- **Id:** S-I01 (also S-H05)
- **Entry point:** `lifeos.api.trash.list` (GET), `lifeos/api/trash.py:8` → `lifeos/library/trash.py:66` `list` → `lifeos/library/trash.py:40` `_rows`.
- **Actor:** an agent (`Life Agent`) that is a member of the space, in a space whose "agents can read the Vault" switch is off.
- **Input:** `space` (any space the agent belongs to).
- **Impact:** for every Vault document deleted in the last 30 days, the agent gets its title, area, record name, who deleted it and when. `_rows` filters by space membership only (`trash.py:54`); it never applies `permissions.vault_hidden`, unlike every other list (`vault_guard`). The same holds for a deleted inbox item a Vault document was made from (`vault_document` set).
- **Proof (bench, rolled back):** as the owner, create a Vault document "milkshake passport audit" in Private (switch off: `agents_can_read_vault = 0`) and delete it with `trash.delete`; as `hermes@lifeos.test`, `trash.list(space="Private")["rows"]` returns `['milkshake passport audit']`. `vault.list` as the same agent returns no Vault document.
- **Fix:** in `trash._rows`, skip a row when `permissions.vault_hidden(space)` and the deleted record is a `Life Vault Document`, or a `Life Inbox Item` with `vault_document` set. Agents are never meant to use the trash (`agent/SKILL.md`), so refusing `trash.list` to agents outright is also acceptable.

### [LOW] Quick add's date pattern takes quadratic time on a run of commas

- **Id:** S-K01
- **Entry point:** `lifeos.api.tasks.quick_add` (POST), `lifeos/api/tasks.py:194` → `lifeos/tasks/datewords.py:76` `parse` → `TAIL` at `lifeos/tasks/datewords.py:15`.
- **Actor:** any person or agent with Write access to a space.
- **Input:** `text`, for example `"a" + "," * 30000 + "x"` (30 KB). `parse` collapses whitespace but not commas, and `^(?P<title>.+?)[\s,]+…$` backtracks over the run.
- **Impact:** one request holds a web worker for minutes (measured on the bench: 2,000 commas 0.7 s, 8,000 commas 11 s, so 30,000 about 2.5 minutes), until the worker timeout. A few requests at once make the site unresponsive.
- **Fix:** cut `text` to a few hundred characters before parsing (the title is cut to 140 anyway), and collapse runs of `[\s,]` to one character before matching.

### [LOW] The chat import reads conversations.json without a limit on its uncompressed size

- **Id:** S-K01
- **Entry point:** `lifeos.api.connections.start_import` (POST) → job `lifeos.brain.chat_import.run` → `conversations_from_zip`, `lifeos/brain/chat_import.py:146` (`json.load` of the zip member).
- **Actor:** a person with Write access to a space.
- **Input:** an uploaded private `.zip` whose `conversations.json` is small compressed and very large uncompressed. Only the compressed size is checked (1 GB, `MAX_ZIP`).
- **Impact:** the long-queue worker reads the whole member into memory and is killed (the bench container has 2.5 GB), stopping other background jobs until it restarts. Bounded by the site's upload limit.
- **Fix:** check `z.getinfo(name).file_size` against a limit (for example 2 GB, or a ratio to the compressed size) before `json.load`, and fail the import with a plain message.

## Refuted or uncertain candidates

- `datewords.parse` with long runs of spaces: refuted, `parse` collapses whitespace first (20,000 words parse in 7 ms).
- `window.open` of digest Gmail links (`DigestView.vue`): refuted for F03, links match a fixed `mail.google.com` pattern; any client-side XSS question belongs to scope C.
- `files.make_preview` and `sources.make_thumbnail` on a huge image: refuted, Pillow raises `DecompressionBombError` above its default pixel limit.
- `trash.restore` by an agent: refuted, it refuses agents and requires Write access to the space.
- `link_query` with a large `page_len`: not a finding, results come through `frappe.get_list` and are limited to what the caller may read.

## S-P01 Endpoint hardening coverage

- **Annotations:** 171 of 171 whitelisted methods declare `methods=[...]` and hint every parameter (100 %; enforced by `test_pre6_conventions`). Loose hints are deliberate where callers send JSON strings or objects (`str | list`, `str | dict`), each parsed with `parse()`.
- **Role checks:** 160 methods check explicitly (`resolve_space`, `require_space`, `get_doc_checked`, `_admin_only`, `_person`, `is_agent`); 10 delegate to a helper or to `insert`/`save` that checks; 1 (`queries.link_query`) reads through `frappe.get_list`, which applies the permission query conditions. No method has no check.
- **Shared helpers:** `permissions.resolve_space` and `get_doc_checked` carry nearly all checks; the trash's `_rows` is the one list that bypasses the Vault rule (finding above).

## S-P02 Invariant diffs (against the app as it stands; no stored baseline)

| Item | Count | Result |
| --- | --- | --- |
| `allow_guest=True` | 0 | pass |
| `shell=True`, `verify=False`, `\|safe`, `jinja` hooks | 0 | pass |
| `ignore_permissions=True` | 61 | warn: each follows an explicit space or record check in the same function, or runs in a job, install or seed; listed for review |
| DocTypes with no permission rows, or rows for All, Guest or Website User | 0 | pass |
| Sandbox globals added | none | not applicable |

## S-P03 Security headers

| Header | Current value (bench serve) | Gap | Level |
| --- | --- | --- | --- |
| Content-Security-Policy | not set | no CSP on `/life` | app-level (the SPA could ship one) and deployment-level |
| X-Frame-Options / frame-ancestors | not set by the app | Frappe's production nginx template sets `X-Frame-Options: SAMEORIGIN` | deployment-level |
| X-Content-Type-Options | not set by the app | set to `nosniff` by Frappe's production nginx template | deployment-level |
| Referrer-Policy | not set | — | deployment-level |
| Strict-Transport-Security | not set | needs HTTPS in front | deployment-level |
| Permissions-Policy | not set | — | deployment-level |

No document field influences a header.

## S-P04 Dependency pinning

- `pyproject.toml`: `anthropic==2.9.0` pinned; `frappe >=16,<17` is a first-party range (policy choice).
- `frontend/package.json`: caret ranges, resolved by the committed `frontend/yarn.lock` (yarn v1, integrity hashes on 361 entries, no git or fork sources). `@framework/ui` links `../../frappe/ui` from the bench, so its code is whatever Frappe version the bench runs (noted in `STATUS.md`).
- `tools/package.json`: resolved by the committed `tools/package-lock.json` (test tooling only).
- The root `package.json` has a `postinstall` that runs `yarn install` in `frontend/` (the app's own script).
- `docker/docker-compose.yml`: `frappe/bench:latest`, `mariadb:11.8` and `redis:7-alpine` are floating tags (local test stack only).

## S-P05 CI/CD

No workflows in the repository (`.github/` absent), so no trigger can run fork code with secrets. Branch protection and organisation settings were not reachable from the checkout. Git history has no committed credentials; `.env` is ignored and was never committed.
