# Scan exceptions

Every finding of Frappe's semgrep rules that stays in the code carries an inline `# nosemgrep: <rule> -- <reason>`.
This list is written from those comments by `python3 tools/scan_exceptions.py`; do not edit it by hand.


| Rule | Exceptions |
| --- | --- |
| frappe-manual-commit | 8 |
| frappe-missing-translate-function-python | 1 |
| frappe-security-file-traversal | 6 |
| frappe-setuser | 16 |
| frappe-sql-format-injection | 86 |
| Total | 117 |

## frappe-manual-commit

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/brain/chat_import.py` | 221 | long background job: progress is saved every 25 conversations |
| `lifeos/install.py` | 63 | after_install: the spaces and index DDL must be kept before install-app goes on |
| `lifeos/install.py` | 152 | a bench execute command: the user and the space are kept when it ends |
| `lifeos/tools/loadtest.py` | 114 | load test: 100,000 seeded rows are committed so the timed reads see them as a real site would |
| `lifeos/tools/loadtest.py` | 258 | load test: the seeded sources and wiki pages are committed so the timed reads see them as a real site would |
| `lifeos/tools/loadtest.py` | 317 | load test: its removal must stick even when run inside a test |
| `lifeos/skills/__init__.py` | 20 | bench execute: keep the examples' last result |
| `lifeos/tools/tidy.py` | 125 | bench execute run: the copies are removed only after the rows that used them are saved |

## frappe-missing-translate-function-python

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/tools/devtools_review.py` | 16 | development tool, never shown in the app |

## frappe-security-file-traversal

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/api/settings.py` | 228 | the site's own backup folder, names only |
| `lifeos/library/files.py` | 90 | local_path keeps the path inside the site's files folders |
| `lifeos/web/pwa.py` | 18 | a fixed file of this app; no part of the path comes from the request |
| `lifeos/brain/sources.py` | 104 | a fixed name in a temporary folder made here |
| `lifeos/brain/sources.py` | 114 | pdftoppm's own output in a temporary folder made here |
| `lifeos/tools/tidy_files.py` | 170 | _path_of keeps the path inside the site's files folders |

## frappe-setuser

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/tools/demo.py` | 85 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 242 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 246 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 314 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 328 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 344 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/devtools_review.py` | 20 | development tool on the acceptance site: the owner-shaped data is made as the owner |
| `lifeos/tools/loadtest.py` | 44 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 136 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 154 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 169 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 273 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 290 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 311 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/skills/runner.py` | 89 | the run is the Life Brain's, a Life Agent; the session user is put back below |
| `lifeos/skills/runner.py` | 103 | back to the user whose request or job it was |

## frappe-sql-format-injection

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/ai/tools.py` | 175 | WHERE, LIKE and score are fixed fragments with numbered placeholders; the model's words, kinds and dates are parameters |
| `lifeos/ai/tools.py` | 317 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter; order is 'asc' or 'desc' only |
| `lifeos/ai/tools.py` | 320 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter |
| `lifeos/ai/tools.py` | 376 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter |
| `lifeos/api/archive.py` | 74 | fixed fragments, std_clause columns checked against meta, vault_guard constant; values are parameters |
| `lifeos/api/ask.py` | 195 | WHERE is one of two fixed fragments; user, space and the search text are parameters |
| `lifeos/api/ask.py` | 200 | WHERE is one of two fixed fragments; user, space and the search text are parameters |
| `lifeos/api/brain.py` | 140 | WHERE is constant SQL plus area_filter; values are parameters |
| `lifeos/api/brain.py` | 146 | WHERE is constant SQL plus area_filter; values are parameters |
| `lifeos/api/brain.py` | 161 | WHERE is constant SQL plus area_filter; values are parameters |
| `lifeos/api/chats.py` | 25 | vault_guard is a constant fragment; values are parameters |
| `lifeos/api/chats.py` | 144 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 150 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 152 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 154 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 259 | sensitive_guard is a constant fragment; values are parameters |
| `lifeos/api/chats.py` | 263 | as above |
| `lifeos/api/everything.py` | 56 | WHERE from fixed fragments (TAB_SQL) and area_filter; every value is a parameter |
| `lifeos/api/everything.py` | 58 | WHERE from fixed fragments (TAB_SQL) and area_filter; every value is a parameter |
| `lifeos/api/goals.py` | 40 | `sp` is one of two constant fragments; values are parameters |
| `lifeos/api/goals.py` | 102 | WHERE from where_clause (TABS map) and std_clause (meta-checked columns); values are parameters |
| `lifeos/api/goals.py` | 111 | WHERE from where_clause (TABS map) and std_clause (meta-checked columns); ORDER from SORTS or std_order |
| `lifeos/api/goals.py` | 183 | SHOWS is a constant map, off is off_clause's fixed SQL; values are parameters |
| `lifeos/api/goals.py` | 417 | `off` is off_clause's fixed SQL; values are parameters |
| `lifeos/api/inbox.py` | 408 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters); order from std_order or the SORTS allowlist |
| `lifeos/api/inbox.py` | 413 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/inbox.py` | 415 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/insights.py` | 79 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/insights.py` | 87 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/insights.py` | 90 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/library.py` | 67 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/library.py` | 73 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/outbox.py` | 56 | the parts are constant SQL; the area condition comes from area_filter; values are parameters |
| `lifeos/api/outbox.py` | 62 | WHERE from _out_where (constant SQL and area_filter); values are parameters |
| `lifeos/api/outbox.py` | 88 | WHERE from _out_where (constant SQL and area_filter); values are parameters |
| `lifeos/api/outbox.py` | 104 | the parts are constant SQL; the area condition comes from area_filter; values are parameters |
| `lifeos/api/people.py` | 47 | the only formatted part is vault_guard's fixed SQL; every value is a parameter |
| `lifeos/api/search.py` | 58 | FIELDS and WHERE are fixed fragments; the search text is the %(q)s parameter |
| `lifeos/api/search.py` | 70 | FIELDS, WHERE and the LIKE placeholders are fixed fragments; each word is a %(wN)s parameter |
| `lifeos/api/settings.py` | 38 | also_in_sql and vault_guard return fixed fragments; space and area are parameters |
| `lifeos/api/someday.py` | 67 | each branch is _sub's fixed SQL over a PARKABLE table, with std_filters columns checked against meta |
| `lifeos/api/someday.py` | 81 | the union as above; `order` and `way` come from fixed allowlists; values are parameters |
| `lifeos/api/sources.py` | 155 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters (TABS and STATUSES are fixed maps |
| `lifeos/api/sources.py` | 158 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/sources.py` | 162 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/sources.py` | 238 | sensitive_guard is a constant fragment; values are parameters |
| `lifeos/api/tasks.py` | 41 | fixed SQL and meta-checked columns only; values are parameters |
| `lifeos/api/tasks.py` | 122 | the WHERE comes from where_clause (fixed fragments); values are parameters |
| `lifeos/api/tasks.py` | 140 | where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters |
| `lifeos/api/tasks.py` | 176 | where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters |
| `lifeos/api/tasks.py` | 231 | ALL_SHOWS is a constant map, base and off are fixed SQL; values are parameters |
| `lifeos/api/tasks.py` | 294 | NO_GOAL is a constant fragment |
| `lifeos/api/tasks.py` | 490 | open_loops_where() is a constant fragment |
| `lifeos/api/timeline.py` | 38 | ROW_FIELDS and vault_guard are constants; callers pass fixed WHERE and ORDER fragments; values are parameters |
| `lifeos/api/timeline.py` | 71 | fixed fragments, std_filters columns checked against meta; values are parameters |
| `lifeos/api/today.py` | 68 | `lens` is area_filter's fixed SQL; values are parameters |
| `lifeos/api/utils.py` | 242 | `base` and the tab conditions are fixed SQL from the list methods; values are parameters |
| `lifeos/api/utils.py` | 281 | columns pass column() (DocType meta), aggregates an allowlist, `base` is fixed SQL; values are parameters |
| `lifeos/api/utils.py` | 284 | as above |
| `lifeos/api/utils.py` | 300 | allowlisted aggregates over meta-checked columns |
| `lifeos/api/utils.py` | 314 | the DocType is one of a fixed list; the condition is area_filter's fixed SQL; values are parameters |
| `lifeos/api/vault.py` | 75 | clause from where_clause: fixed fragments, the EXPIRY allowlist and area_filter; every value is a parameter |
| `lifeos/api/vault.py` | 115 | columns and filters checked against the DocType meta, order from std_order or the SORTS allowlist; values are parameters |
| `lifeos/api/vault.py` | 119 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/wiki.py` | 178 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 183 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 209 | WHERE from fixed fragments and area_filter; the order comes from a fixed map; values are parameters |
| `lifeos/api/wiki.py` | 213 | WHERE from fixed fragments and area_filter; values are parameters |
| `lifeos/api/wiki.py` | 251 | WHERE from fixed fragments and vault_guard; the search text is the %(q)s parameter |
| `lifeos/api/wiki.py` | 256 | WHERE and LIKE placeholders are fixed fragments; each word is a %(wN)s parameter |
| `lifeos/api/wiki.py` | 447 | CHANGE_FIELDS is a fixed list; WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 450 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/library/archive.py` | 14 | the table is one of ORG_DOCTYPES (checked above) and `where` a fixed fragment; values are parameters |
| `lifeos/library/archive.py` | 76 | `dt` comes from the constant ORG_DOCTYPES |
| `lifeos/library/archive.py` | 89 | `dt` comes from the constant ORG_DOCTYPES |
| `lifeos/tools/devtools.py` | 68 | development tool: dt comes from the SPACE_DOCTYPES constant; values are parameters |
| `lifeos/tools/devtools.py` | 73 | development tool: table names from SPACE_DOCTYPES and their meta's table fields; values are parameters |
| `lifeos/tools/devtools.py` | 76 | development tool: dt comes from the SPACE_DOCTYPES constant; space is a parameter |
| `lifeos/tools/devtools.py` | 218 | development tool: DocType and field from the _TITLED constant |
| `lifeos/tools/devtools.py` | 268 | development tool: dt is checked to be an existing DocType with a table; values are parameters |
| `lifeos/tools/devtools.py` | 291 | development tool: child table names from the meta of a checked DocType; values are parameters |
| `lifeos/tools/devtools.py` | 304 | development tool: dt is checked to be an existing DocType; names are a parameter |
| `lifeos/library/index.py` | 85 | column names come from the fixed COLUMNS list; every value is a %s parameter |
| `lifeos/review/insights.py` | 178 | only the code-owned vault fragment of the tool context is inserted; the rest are parameters |
| `lifeos/brain/old_inbox.py` | 227 | WHERE is constant SQL plus area_filter's fixed fragment; values are parameters |
| `lifeos/review/library.py` | 136 | dt and the date column come from the fixed tuple above; values are parameters |
