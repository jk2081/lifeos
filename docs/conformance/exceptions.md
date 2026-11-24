# Scan exceptions

Every finding of Frappe's semgrep rules that stays in the code carries an inline `# nosemgrep: <rule> -- <reason>`.
This list is written from those comments by `python3 tools/scan_exceptions.py`; do not edit it by hand.


| Rule | Exceptions |
| --- | --- |
| frappe-manual-commit | 15 |
| frappe-missing-translate-function-python | 1 |
| frappe-security-file-traversal | 7 |
| frappe-setuser | 16 |
| frappe-sql-format-injection | 1 |
| guest-whitelisted-method | 1 |
| whitelisted-side-effect-on-get | 1 |
| Total | 42 |

## frappe-manual-commit

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/api/connections.py` | 490 | Frappe's return address is a GET and rolls back at its end; the card must keep what the provider said |
| `lifeos/brain/chat_import.py` | 221 | long background job: progress is saved every 25 conversations |
| `lifeos/install.py` | 70 | after_install: the spaces and index DDL must be kept before install-app goes on |
| `lifeos/install.py` | 159 | a bench execute command: the user and the space are kept when it ends |
| `lifeos/skills/__init__.py` | 20 | bench execute: keep the examples' last result |
| `lifeos/tests/test_settings.py` | 996 | the runner under test commits, so the test cleans up with a commit |
| `lifeos/tools/loadtest.py` | 116 | load test: 100,000 seeded rows are committed so the timed reads see them as a real site would |
| `lifeos/tools/loadtest.py` | 260 | load test: the seeded sources and wiki pages are committed so the timed reads see them as a real site would |
| `lifeos/tools/loadtest.py` | 319 | load test: its removal must stick even when run inside a test |
| `lifeos/tools/tidy.py` | 125 | bench execute run: the copies are removed only after the rows that used them are saved |
| `lifeos/updater/runner.py` | 54 | the runner is a background process: each step's outcome is saved at once |
| `lifeos/updater/runner.py` | 71 | the runner is a background process: each step's outcome is saved at once |
| `lifeos/updater/runner.py` | 92 | the runner is a background process: each step's outcome is saved at once |
| `lifeos/updater/runner.py` | 184 | the runner is a background process: each step's outcome is saved at once |
| `lifeos/updater/runner.py` | 296 | the runner is a background process: a fresh view of the table |

## frappe-missing-translate-function-python

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/tools/devtools_review.py` | 16 | development tool, never shown in the app |

## frappe-security-file-traversal

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/api/settings.py` | 237 | the site's own backup folder, names only |
| `lifeos/brain/sources.py` | 107 | a fixed name in a temporary folder made here |
| `lifeos/brain/sources.py` | 117 | pdftoppm's own output in a temporary folder made here |
| `lifeos/brain/video.py` | 38 | ffmpeg's own output in a temporary folder made here |
| `lifeos/library/files.py` | 90 | local_path keeps the path inside the site's files folders |
| `lifeos/tools/tidy_files.py` | 170 | _path_of keeps the path inside the site's files folders |
| `lifeos/web/pwa.py` | 18 | a fixed file of this app; no part of the path comes from the request |

## frappe-setuser

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/skills/runner.py` | 91 | the run is the Life Brain's, a Life Agent; the session user is put back below |
| `lifeos/skills/runner.py` | 105 | back to the user whose request or job it was |
| `lifeos/tools/demo.py` | 104 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 261 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 265 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 333 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 347 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/demo.py` | 363 | demo data: records are made through the API as the owner and the agent would make them |
| `lifeos/tools/devtools_review.py` | 20 | development tool on the acceptance site: the owner-shaped data is made as the owner |
| `lifeos/tools/loadtest.py` | 46 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 138 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 156 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 171 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 275 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 292 | load test: reads are timed as a member of the space, the way a request runs |
| `lifeos/tools/loadtest.py` | 313 | load test: reads are timed as a member of the space, the way a request runs |

## frappe-sql-format-injection

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/library/index.py` | 86 | column names come from the fixed COLUMNS list; every value is a %s parameter |

## guest-whitelisted-method

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/api/connections.py` | 470 | the same door as Frappe's own callback, which sends a guest to log in |

## whitelisted-side-effect-on-get

| File | Line | Reason |
| --- | --- | --- |
| `lifeos/api/connections.py` | 490 | Frappe's return address is a GET and rolls back at its end; the card must keep what the provider said |
