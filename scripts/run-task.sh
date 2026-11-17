#!/bin/bash
# Run one follow-up task file unattended, for example:  ./scripts/run-task.sh UX_FIXES_1.md
# The task file must end by creating <NAME>_DONE (for UX_FIXES_1.md that is UX_FIXES_1_DONE).
set -u
cd "$(dirname "$0")/.."
TASK="${1:?Usage: ./scripts/run-task.sh TASK_FILE.md}"
[ -f "$TASK" ] || { echo "No such file: $TASK"; exit 1; }
MODEL="${MODEL:-fable}"; PERMISSION_MODE="${PERMISSION_MODE:-auto}"; MAX_ROUNDS="${MAX_ROUNDS:-6}"
DONE="$(basename "$TASK" .md)_DONE"
LOG_DIR="build-logs"; mkdir -p "$LOG_DIR"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_DIR/build.log"; }
command -v claude >/dev/null || { echo "Claude Code is not installed."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running. Open Docker Desktop first."; exit 1; }
if command -v caffeinate >/dev/null; then caffeinate -i -w $$ & fi
./scripts/get-frappe-skills.sh || echo "Could not fetch Frappe skills; continuing with any copy already in .claude/skills."
PROMPT="Nobody is watching this run. Do not ask questions and do not wait for input.

Read CLAUDE.md, STATUS.md and DECISIONS.md. Start the local stack as STATUS.md describes and check that the site and the tests work. Then carry out every item in $TASK, in order, following its working rules. If part of it is already done, check it and continue with the rest. When everything in it is finished and its checks pass, create an empty file named $DONE and commit. If you cannot go further, write the reason to BUILD_BLOCKED, commit, and stop.

Do not stop, restart, remove or change any Docker container, image, volume or network whose name does not start with lifeos-."
START_SHA="$(git rev-parse HEAD)"; START_TIME=$(date +%s); ROUND_FILE="$LOG_DIR/.round"; echo 1 > "$ROUND_FILE"
# A progress line every few minutes (UPDATE_EVERY seconds, default 300): in this window, in build-logs/build.log,
# as a Mac notification, and pushed to GitHub so the commits can be followed from a phone.
heartbeat() {
  while sleep "${UPDATE_EVERY:-300}"; do
    commits=$(git rev-list --count "$START_SHA"..HEAD 2>/dev/null || echo 0)
    latest=$(git log -1 --format='%s (%cr)' 2>/dev/null | cut -c1-90)
    editing=$(git --no-optional-locks status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    mins=$(( ($(date +%s) - START_TIME) / 60 ))
    line="Update at ${mins} min: round $(cat "$ROUND_FILE"), $commits steps committed, $editing files being edited. Latest: $latest"
    say "$line"
    command -v osascript >/dev/null && osascript -e "display notification \"${line//\"/}\" with title \"Life OS build\"" >/dev/null 2>&1
    git push -q origin HEAD >/dev/null 2>&1
  done
}
heartbeat & HEARTBEAT=$!
trap 'kill $HEARTBEAT 2>/dev/null' EXIT
round=1
while [ "$round" -le "$MAX_ROUNDS" ] && [ ! -f "$DONE" ] && [ ! -f BUILD_BLOCKED ]; do
  say "Task $TASK, round $round"
  echo "$round" > "$ROUND_FILE"
  started=$(date +%s)
  claude -p "$PROMPT" --model "$MODEL" --permission-mode "$PERMISSION_MODE" --verbose > "$LOG_DIR/$(basename "$TASK" .md)-round-$round.log" 2>&1
  elapsed=$(( $(date +%s) - started ))
  say "Round $round ended after $((elapsed / 60)) minutes."
  [ -n "$(git status --porcelain)" ] && { git add -A && git commit -q -m "$(basename "$TASK" .md) round $round: uncommitted work saved" || true; }
  git push -q origin HEAD 2>>"$LOG_DIR/build.log" && say "Pushed to GitHub." || say "Push failed. Work is committed locally."
  if [ "$elapsed" -lt 300 ] && [ ! -f "$DONE" ]; then tail -n 5 "$LOG_DIR/$(basename "$TASK" .md)-round-$round.log" | tee -a "$LOG_DIR/build.log"; say "Short round. Waiting 30 minutes."; sleep 1800; fi
  round=$((round + 1))
done
if [ -f "$DONE" ]; then say "Result: $TASK finished. Read STATUS.md."; elif [ -f BUILD_BLOCKED ]; then say "Result: blocked. Read BUILD_BLOCKED."; else say "Result: not finished after $MAX_ROUNDS rounds. Run this again to continue."; fi
