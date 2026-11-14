#!/bin/bash
# Unattended build of Life OS with Claude Code. Run from the repo root:  ./scripts/start-build.sh
# It keeps the Mac awake, runs Claude Code headless in rounds until the build is
# finished or blocked, logs everything to build-logs/, and pushes after each round.
set -u
cd "$(dirname "$0")/.."

MODEL="${MODEL:-fable}"
PERMISSION_MODE="${PERMISSION_MODE:-auto}"
MAX_ROUNDS="${MAX_ROUNDS:-12}"
LOG_DIR="build-logs"
mkdir -p "$LOG_DIR"

say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_DIR/build.log"; }

command -v claude >/dev/null || { echo "Claude Code is not installed. Install it, then run this again."; exit 1; }
command -v git >/dev/null || { echo "git is not installed."; exit 1; }
BENCH_PATH="${BENCH_PATH:-}"
EXTRA=""
if [ -n "$BENCH_PATH" ]; then
  BENCH_PATH="$(cd "$BENCH_PATH" 2>/dev/null && pwd)" || { echo "BENCH_PATH does not exist."; exit 1; }
  [ -d "$BENCH_PATH/apps/frappe" ] || { echo "$BENCH_PATH does not look like a Frappe bench (no apps/frappe)."; exit 1; }
  EXTRA="

BENCH OVERRIDE. Do not use Docker. Use the existing Frappe bench at $BENCH_PATH instead.
- First check that its Frappe version is 16. If it is not, write the reason to BUILD_BLOCKED and stop.
- Create one new site named lifeos.localhost on that bench and use only that site. Never touch, migrate, back up, restore or drop any other site.
- Do not run bench update, do not switch branches or change versions of any existing app, and do not remove or reinstall any app. Only add the lifeos app, with bench get-app from this repository's folder or a symlink.
- Do not change common_site_config.json except to add what a new site strictly needs, and record any such change in DECISIONS.md.
- If the bench processes are not running, start what you need yourself and stop only what you started."
else
command -v docker >/dev/null || { echo "Docker is not installed. Install Docker Desktop, or run with BENCH_PATH=/path/to/frappe-bench to use an existing bench."; exit 1; }
fi

if [ -z "$BENCH_PATH" ] && ! docker info >/dev/null 2>&1; then
  say "Docker is not running. Trying to start Docker Desktop."
  open -a Docker 2>/dev/null || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
  docker info >/dev/null 2>&1 || { say "Docker did not start. Open Docker Desktop and run this again."; exit 1; }
fi

# Keep the Mac awake for as long as this script runs (macOS only).
if command -v caffeinate >/dev/null; then caffeinate -i -w $$ & fi

say "Bench: ${BENCH_PATH:-Docker}."
say "Build started. Model: $MODEL. Permission mode: $PERMISSION_MODE. Up to $MAX_ROUNDS rounds."

round=1
while [ "$round" -le "$MAX_ROUNDS" ]; do
  if [ -f BUILD_DONE ]; then say "BUILD_DONE found. Finished."; break; fi
  if [ -f BUILD_BLOCKED ]; then say "BUILD_BLOCKED found. See the file for the reason."; break; fi

  if [ "$round" -eq 1 ] && [ ! -f STATUS.md ]; then prompt_file="START_PROMPT.md"; else prompt_file="CONTINUE_PROMPT.md"; fi
  say "Round $round, using $prompt_file"
  started=$(date +%s)

  claude -p "$(cat "$prompt_file")$EXTRA" \
    --model "$MODEL" \
    --permission-mode "$PERMISSION_MODE" \
    --verbose \
    ${BENCH_PATH:+--add-dir "$BENCH_PATH"} \
    > "$LOG_DIR/round-$round.log" 2>&1
  code=$?
  elapsed=$(( $(date +%s) - started ))
  say "Round $round ended with exit code $code after $((elapsed / 60)) minutes."

  # Save whatever was built, even if the round ended badly.
  if [ -n "$(git status --porcelain)" ]; then
    git add -A && git commit -q -m "Build round $round: uncommitted work saved by start-build.sh" || true
  fi
  git push -q origin HEAD 2>>"$LOG_DIR/build.log" && say "Pushed to GitHub." || say "Push failed. Work is committed locally."

  # A round that ends within 5 minutes usually means a usage limit or a start-up error. Wait before retrying.
  if [ "$elapsed" -lt 300 ]; then
    say "Round was very short. Last lines of its log:"
    tail -n 5 "$LOG_DIR/round-$round.log" | tee -a "$LOG_DIR/build.log"
    say "Waiting 30 minutes before the next round."
    sleep 1800
  fi
  round=$((round + 1))
done

if [ -f BUILD_DONE ]; then say "Result: build complete. Read STATUS.md."
elif [ -f BUILD_BLOCKED ]; then say "Result: build blocked. Read BUILD_BLOCKED and STATUS.md."
else say "Result: stopped after $MAX_ROUNDS rounds without finishing. Read STATUS.md, then run this script again to continue."
fi
