#!/bin/bash
# Scan Life OS with Frappe's semgrep rules (github.com/frappe/semgrep-rules).
#
#   tools/scan.sh                 scan lifeos/
#   tools/scan.sh FILE...         scan only these files (paths relative to the repo root)
#   tools/scan.sh --json FILE...  print semgrep's JSON instead of the summary
#
# Semgrep runs inside the lifeos-bench container (installed there with pip when missing), so the
# owner's Mac needs only Docker. The rules are pinned to RULES_REF and cached in .cache/ (git-ignored).
# Exits non-zero on any finding. An unavoidable finding carries an inline `# nosemgrep: <rule>` with
# the reason, and is listed in docs/conformance/exceptions.md.
set -eu
cd "$(dirname "$0")/.."
RULES_REF="${FRAPPE_SEMGREP_REF:-81a6e3d47a328249e8ddf04c586e493dd5553002}"
RULES=".cache/frappe-semgrep-rules"
CONTAINER="${LIFEOS_BENCH:-lifeos-bench}"
APP_IN_CONTAINER="/home/frappe/frappe-bench/apps/lifeos"

JSON=0
if [ "${1:-}" = "--json" ]; then JSON=1; shift; fi

if [ ! -d "$RULES/.git" ]; then
  mkdir -p .cache
  git clone -q https://github.com/frappe/semgrep-rules "$RULES"
fi
if [ "$(git -C "$RULES" rev-parse HEAD)" != "$RULES_REF" ]; then
  git -C "$RULES" fetch -q origin 2>/dev/null || true
  git -C "$RULES" checkout -q "$RULES_REF"
fi

if [ "$#" -eq 0 ]; then set -- lifeos; fi

docker exec "$CONTAINER" bash -lc 'command -v semgrep >/dev/null || python3 -m pip install -q --user semgrep' >&2

# Semgrep reads .gitignore and .semgrepignore, so the built front end and node_modules are skipped.
OUT=$(docker exec -w "$APP_IN_CONTAINER" "$CONTAINER" bash -lc \
  "semgrep scan --metrics=off --quiet --json --config $RULES/rules $(printf '%q ' "$@")" || true)

if [ "$JSON" = 1 ]; then
  printf '%s\n' "$OUT"
  printf '%s' "$OUT" | python3 tools/scan_summary.py --quiet
else
  printf '%s' "$OUT" | python3 tools/scan_summary.py
fi
