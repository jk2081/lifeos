# Scan exceptions

Every finding of Frappe's semgrep rules that stays in the code carries an inline `# nosemgrep: <rule> -- <reason>`.
This list is written from those comments by `python3 tools/scan_exceptions.py`; do not edit it by hand.


| Rule | Exceptions |
| --- | --- |
| frappe-manual-commit | 5 |
| frappe-security-file-traversal | 4 |
| frappe-setuser | 13 |
| frappe-sql-format-injection | 73 |
| Total | 95 |

## frappe-manual-commit

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/chat_import.py` | 221 | long background job: progress is saved every 25 conversations |
| `lifeos/install.py` | 27 | after_install: the spaces and index DDL must be kept before install-app goes on |
| `lifeos/loadtest.py` | 114 | load test: 100,000 seeded rows are committed so the timed reads see them as a real site would |
| `lifeos/loadtest.py` | 258 | load test: the seeded sources and wiki pages are committed so the timed reads see them as a real site would |
| `lifeos/loadtest.py` | 317 | load test: its removal must stick even when run inside a test |

## frappe-security-file-traversal

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/api/settings.py` | 182 | the site's own backup folder, names only |
| `lifeos/files.py` | 74 | local_path keeps the path inside the site's files folders |
| `lifeos/sources.py` | 102 | a fixed name in a temporary folder made here |
| `lifeos/sources.py` | 112 | pdftoppm's own output in a temporary folder made here |

## frappe-setuser

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/demo.py` | 32 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/demo.py` | 195 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/demo.py` | 199 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/demo.py` | 245 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/demo.py` | 259 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/demo.py` | 275 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/loadtest.py` | 44 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/loadtest.py` | 136 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/loadtest.py` | 154 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/loadtest.py` | 169 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/loadtest.py` | 273 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/loadtest.py` | 290 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/loadtest.py` | 311 | load test: reads are timed as a member of the space, the way a request runs |

## frappe-sql-format-injection

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/ai/insights.py` | 37 | only the code-owned vault fragment of the tool context is inserted; space, date and limit are parameters |
| `lifeos/ai/tools.py` | 176 | WHERE, LIKE and score are fixed fragments with numbered placeholders; the model's words, kinds and dates are parameters |
| `lifeos/ai/tools.py` | 318 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter; order is 'asc' or 'desc' only |
| `lifeos/ai/tools.py` | 321 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter |
| `lifeos/ai/tools.py` | 377 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter |
| `lifeos/api/archive.py` | 74 | fixed fragments, std_clause columns checked against meta, vault_guard constant; values are parameters |
| `lifeos/api/ask.py` | 195 | WHERE is one of two fixed fragments; user, space and the search text are parameters |
| `lifeos/api/ask.py` | 200 | WHERE is one of two fixed fragments; user, space and the search text are parameters |
| `lifeos/api/chats.py` | 147 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 153 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 155 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 157 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 263 | sensitive_guard is a constant fragment; values are parameters |
| `lifeos/api/chats.py` | 267 | as above |
| `lifeos/api/goals.py` | 36 | `sp` is one of two constant fragments; values are parameters |
| `lifeos/api/goals.py` | 96 | WHERE from where_clause (TABS map) and std_clause (meta-checked columns); values are parameters |
| `lifeos/api/goals.py` | 105 | WHERE from where_clause (TABS map) and std_clause (meta-checked columns); ORDER from SORTS or std_order |
| `lifeos/api/inbox.py` | 298 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters); order from std_order or the SORTS allowlist |
| `lifeos/api/inbox.py` | 303 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/inbox.py` | 305 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/insights.py` | 79 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/insights.py` | 87 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/insights.py` | 90 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/library.py` | 73 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/library.py` | 78 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/search.py` | 58 | FIELDS and WHERE are fixed fragments; the search text is the %(q)s parameter |
| `lifeos/api/search.py` | 70 | FIELDS, WHERE and the LIKE placeholders are fixed fragments; each word is a %(wN)s parameter |
| `lifeos/api/settings.py` | 36 | also_in_sql and vault_guard return fixed fragments; space and area are parameters |
| `lifeos/api/someday.py` | 71 | each branch is _sub's fixed SQL over a PARKABLE table, with std_filters columns checked against meta |
| `lifeos/api/someday.py` | 85 | the union as above; `order` and `way` come from fixed allowlists; values are parameters |
| `lifeos/api/sources.py` | 160 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters (TABS and STATUSES are fixed maps |
| `lifeos/api/sources.py` | 163 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/sources.py` | 167 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/tasks.py` | 45 | fixed SQL and meta-checked columns only; values are parameters |
| `lifeos/api/tasks.py` | 131 | the WHERE comes from where_clause (fixed fragments); values are parameters |
| `lifeos/api/tasks.py` | 149 | where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters |
| `lifeos/api/tasks.py` | 185 | where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters |
| `lifeos/api/tasks.py` | 271 | open_loops_where() is a constant fragment |
| `lifeos/api/timeline.py` | 38 | ROW_FIELDS and vault_guard are constants; callers pass fixed WHERE and ORDER fragments; values are parameters |
| `lifeos/api/timeline.py` | 71 | fixed fragments, std_filters columns checked against meta; values are parameters |
| `lifeos/api/today.py` | 54 | `lens` is area_filter's fixed SQL; values are parameters |
| `lifeos/api/utils.py` | 242 | `base` and the tab conditions are fixed SQL from the list methods; values are parameters |
| `lifeos/api/utils.py` | 281 | columns pass column() (DocType meta), aggregates an allowlist, `base` is fixed SQL; values are parameters |
| `lifeos/api/utils.py` | 284 | as above |
| `lifeos/api/utils.py` | 300 | allowlisted aggregates over meta-checked columns |
| `lifeos/api/utils.py` | 314 | the DocType is one of a fixed list; the condition is area_filter's fixed SQL; values are parameters |
| `lifeos/api/vault.py` | 76 | clause from where_clause: fixed fragments, the EXPIRY allowlist and area_filter; every value is a parameter |
| `lifeos/api/vault.py` | 118 | columns and filters checked against the DocType meta, order from std_order or the SORTS allowlist; values are parameters |
| `lifeos/api/vault.py` | 122 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/wiki.py` | 181 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 186 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 212 | WHERE from fixed fragments and area_filter; the order comes from a fixed map; values are parameters |
| `lifeos/api/wiki.py` | 216 | WHERE from fixed fragments and area_filter; values are parameters |
| `lifeos/api/wiki.py` | 254 | WHERE from fixed fragments and vault_guard; the search text is the %(q)s parameter |
| `lifeos/api/wiki.py` | 259 | WHERE and LIKE placeholders are fixed fragments; each word is a %(wN)s parameter |
| `lifeos/api/wiki.py` | 434 | CHANGE_FIELDS is a fixed list; WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 437 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/archive.py` | 14 | the table is one of ORG_DOCTYPES (checked above) and `where` a fixed fragment; values are parameters |
| `lifeos/archive.py` | 76 | `dt` comes from the constant ORG_DOCTYPES |
| `lifeos/archive.py` | 89 | `dt` comes from the constant ORG_DOCTYPES |
| `lifeos/devtools.py` | 59 | development tool: dt comes from the SPACE_DOCTYPES constant; values are parameters |
| `lifeos/devtools.py` | 64 | development tool: table names from SPACE_DOCTYPES and their meta's table fields; values are parameters |
| `lifeos/devtools.py` | 67 | development tool: dt comes from the SPACE_DOCTYPES constant; space is a parameter |
| `lifeos/devtools.py` | 198 | development tool: DocType and field from the _TITLED constant |
| `lifeos/devtools.py` | 248 | development tool: dt is checked to be an existing DocType with a table; values are parameters |
| `lifeos/devtools.py` | 273 | development tool: child table names from the meta of a checked DocType; values are parameters |
| `lifeos/devtools.py` | 283 | development tool: dt is checked to be an existing DocType; names are a parameter |
| `lifeos/index.py` | 97 | column names come from the fixed COLUMNS list; every value is a %s parameter |
| `lifeos/patches/v7/projects_into_goals.py` | 151 | `dt` comes from the constant RENAMED |
| `lifeos/patches/v7/projects_into_goals.py` | 170 | `end` is "from" or "to" |
| `lifeos/patches/v7/projects_into_goals.py` | 180 | DocType and field names come from the constant DYNAMIC |
| `lifeos/patches/v7/projects_into_goals.py` | 248 | `dt` comes from index.KINDS, a constant |
| `lifeos/tests/test_ux6_goals.py` | 24 | `doctype` comes from the constant OLD_COLUMNS |
