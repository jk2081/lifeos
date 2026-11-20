#!/bin/bash
# Scan Life OS with Frappe's semgrep rules (github.com/frappe/semgrep-rules).
#
#   tools/scan.sh                 scan lifeos/
#   tools/scan.sh FILE...         scan only these files (paths relative to the repo root)
#   tools/scan.sh --json FILE...  print semgrep's JSON instead of the summary
#
# Semgrep runs inside the lifeos-bench container through tools/bench.sh (installed there with pip when
# missing), so the owner's Mac needs only Docker. With LIFEOS_BENCH_CMD=local (GitHub Actions) it runs here,
# over this checkout, and must be installed already. The rules are pinned to RULES_REF and cached in .cache/
# (git-ignored).
# Exits non-zero on any finding. An unavoidable finding carries an inline `# nosemgrep: <rule>` with
# the reason, and is listed in docs/conformance/exceptions.md.
set -eu
cd "$(dirname "$0")/.."
RULES_REF="${FRAPPE_SEMGREP_REF:-81a6e3d47a328249e8ddf04c586e493dd5553002}"
RULES=".cache/frappe-semgrep-rules"

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

# Semgrep reads .gitignore and .semgrepignore, so the built front end and node_modules are skipped.
if [ "${LIFEOS_BENCH_CMD:-docker}" = local ]; then
  OUT=$(semgrep scan --metrics=off --quiet --json --config "$RULES/rules" "$@" || true)
else
  tools/bench.sh 'command -v semgrep >/dev/null || python3 -m pip install -q --user semgrep' >&2
  OUT=$(tools/bench.sh \
    "cd apps/lifeos && semgrep scan --metrics=off --quiet --json --config $RULES/rules $(printf '%q ' "$@")" || true)
fi

if [ "$JSON" = 1 ]; then
  printf '%s\n' "$OUT"
  printf '%s' "$OUT" | python3 tools/scan_summary.py --quiet
else
  printf '%s' "$OUT" | python3 tools/scan_summary.py
fi
