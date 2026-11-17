#!/bin/bash
# Fetch Frappe's official agent skills (github.com/frappe/skills) into .claude/skills/, where Claude Code
# loads project skills. They are fetched, not committed: the repository publishes no licence for copying.
# Pinned to a known commit; change FRAPPE_SKILLS_REF to update.
set -eu
cd "$(dirname "$0")/.."
REF="${FRAPPE_SKILLS_REF:-d213dce39942c969293e9fe7feb96ab33cbba25c}"
SKILLS="frappe-app-dev frappe-code-review code-style ui-design deep-app-audit"
CACHE=".cache/frappe-skills"
if [ ! -d "$CACHE/.git" ]; then
  mkdir -p .cache
  git clone -q https://github.com/frappe/skills "$CACHE"
fi
git -C "$CACHE" fetch -q origin 2>/dev/null || true
git -C "$CACHE" checkout -q "$REF"
mkdir -p .claude/skills
for s in $SKILLS; do
  rm -rf ".claude/skills/$s"
  cp -R "$CACHE/skills/$s" ".claude/skills/$s"
done
echo "Frappe skills at $REF: $SKILLS"
