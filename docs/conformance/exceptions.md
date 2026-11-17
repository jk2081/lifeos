# Scan exceptions

Every finding of Frappe's semgrep rules that stays in the code carries an inline `# nosemgrep: <rule> -- <reason>`.
This list is written from those comments by `python3 tools/scan_exceptions.py`; do not edit it by hand.


| Rule | Exceptions |
| --- | --- |
| frappe-sql-format-injection | 68 |
| Total | 68 |

## frappe-sql-format-injection

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/ai/insights.py` | 37 | only the code-owned vault fragment of the tool context is inserted; space, date and limit are parameters |
| `lifeos/ai/tools.py` | 178 | WHERE, LIKE and score are fixed fragments with numbered placeholders; the model's words, kinds and dates are parameters |
| `lifeos/ai/tools.py` | 320 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter; order is 'asc' or 'desc' only |
| `lifeos/ai/tools.py` | 323 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter |
| `lifeos/ai/tools.py` | 377 | fixed fragments (vault and scope SQL from the tool context, code-owned); every value, including model-chosen ones, is a parameter |
| `lifeos/api/archive.py` | 74 | fixed fragments, std_clause columns checked against meta, vault_guard constant; values are parameters |
| `lifeos/api/area.py` | 12 | callers pass fixed WHERE fragments; values are parameters |
| `lifeos/api/area.py` | 53 | `arch` and vault_guard are constant fragments |
| `lifeos/api/area.py` | 56 | `arch` is a constant fragment |
| `lifeos/api/ask.py` | 186 | WHERE is one of two fixed fragments; user, space and the search text are parameters |
| `lifeos/api/ask.py` | 191 | WHERE is one of two fixed fragments; user, space and the search text are parameters |
| `lifeos/api/chats.py` | 140 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 146 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 148 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/chats.py` | 150 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/goals.py` | 35 | `sp` is one of two constant fragments; values are parameters |
| `lifeos/api/goals.py` | 91 | WHERE from where_clause (TABS map) and std_clause (meta-checked columns); values are parameters |
| `lifeos/api/inbox.py` | 293 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters); order from std_order or the SORTS allowlist |
| `lifeos/api/inbox.py` | 298 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/inbox.py` | 300 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/insights.py` | 79 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/insights.py` | 87 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/insights.py` | 90 | WHERE is joined from fixed fragments; every value is a parameter |
| `lifeos/api/library.py` | 63 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/library.py` | 68 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/projects.py` | 46 | the WHERE comes from where_clause (fixed fragments); values are parameters |
| `lifeos/api/projects.py` | 78 | where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters |
| `lifeos/api/projects.py` | 100 | `arch` and vault_guard are constant fragments |
| `lifeos/api/search.py` | 54 | FIELDS and WHERE are fixed fragments; the search text is the %(q)s parameter |
| `lifeos/api/search.py` | 66 | FIELDS, WHERE and the LIKE placeholders are fixed fragments; each word is a %(wN)s parameter |
| `lifeos/api/settings.py` | 33 | also_in_sql and vault_guard return fixed fragments; space and area are parameters |
| `lifeos/api/someday.py` | 68 | each branch is _sub's fixed SQL over a PARKABLE table, with std_filters columns checked against meta |
| `lifeos/api/someday.py` | 82 | the union as above; `order` and `way` come from fixed allowlists; values are parameters |
| `lifeos/api/sources.py` | 126 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters (TABS and STATUSES are fixed maps |
| `lifeos/api/sources.py` | 129 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/sources.py` | 133 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/tasks.py` | 45 | fixed SQL and meta-checked columns only; values are parameters |
| `lifeos/api/tasks.py` | 132 | the WHERE comes from where_clause (fixed fragments); values are parameters |
| `lifeos/api/tasks.py` | 170 | where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters |
| `lifeos/api/tasks.py` | 253 | open_loops_where() is a constant fragment |
| `lifeos/api/timeline.py` | 38 | ROW_FIELDS and vault_guard are constants; callers pass fixed WHERE and ORDER fragments; values are parameters |
| `lifeos/api/timeline.py` | 74 | fixed fragments, std_filters columns checked against meta; values are parameters |
| `lifeos/api/utils.py` | 224 | `base` and the tab conditions are fixed SQL from the list methods; values are parameters |
| `lifeos/api/utils.py` | 263 | columns pass column() (DocType meta), aggregates an allowlist, `base` is fixed SQL; values are parameters |
| `lifeos/api/utils.py` | 266 | as above |
| `lifeos/api/utils.py` | 282 | allowlisted aggregates over meta-checked columns |
| `lifeos/api/vault.py` | 75 | clause from where_clause: fixed fragments, the EXPIRY allowlist and area_filter; every value is a parameter |
| `lifeos/api/vault.py` | 115 | columns and filters checked against the DocType meta, order from std_order or the SORTS allowlist; values are parameters |
| `lifeos/api/vault.py` | 119 | clause from fixed fragments and std_filters (columns checked against meta, values as parameters |
| `lifeos/api/wiki.py` | 177 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 182 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 208 | WHERE from fixed fragments and area_filter; the order comes from a fixed map; values are parameters |
| `lifeos/api/wiki.py` | 212 | WHERE from fixed fragments and area_filter; values are parameters |
| `lifeos/api/wiki.py` | 250 | WHERE from fixed fragments and vault_guard; the search text is the %(q)s parameter |
| `lifeos/api/wiki.py` | 255 | WHERE and LIKE placeholders are fixed fragments; each word is a %(wN)s parameter |
| `lifeos/api/wiki.py` | 429 | CHANGE_FIELDS is a fixed list; WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/api/wiki.py` | 432 | WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters |
| `lifeos/archive.py` | 14 | the table is one of ORG_DOCTYPES (checked above) and `where` a fixed fragment; values are parameters |
| `lifeos/archive.py` | 76 | `dt` comes from the constant ORG_DOCTYPES |
| `lifeos/archive.py` | 89 | `dt` comes from the constant ORG_DOCTYPES |
| `lifeos/devtools.py` | 61 | development tool: dt comes from the SPACE_DOCTYPES constant; values are parameters |
| `lifeos/devtools.py` | 66 | development tool: table names from SPACE_DOCTYPES and their meta's table fields; values are parameters |
| `lifeos/devtools.py` | 69 | development tool: dt comes from the SPACE_DOCTYPES constant; space is a parameter |
| `lifeos/devtools.py` | 201 | development tool: DocType and field from the _TITLED constant |
| `lifeos/devtools.py` | 251 | development tool: dt is checked to be an existing DocType with a table; values are parameters |
| `lifeos/devtools.py` | 276 | development tool: child table names from the meta of a checked DocType; values are parameters |
| `lifeos/devtools.py` | 286 | development tool: dt is checked to be an existing DocType; names are a parameter |
| `lifeos/index.py` | 97 | column names come from the fixed COLUMNS list; every value is a %s parameter |
