#!/bin/bash
# Work through the GitHub issues labelled `ready`, one at a time, unattended, until none are left.
#
#   ./scripts/run-issues.sh          every open `ready` issue, lowest number first
#   ./scripts/run-issues.sh 12 15    only these issues, in this order
#
# For each issue: a branch from the latest main, Claude Code in rounds until the issue is done or blocked
# (docs/ISSUE_RULES.md), a pull request that closes the issue, GitHub Actions on it, and a merge when CI is green.
# A blocked issue gets a comment and the `blocked` label, and the runner moves on to the next one.
# An issue whose body says "**Needs:** #a, #b" waits until those issues are closed. Issues labelled blocked, in-progress,
# in-review (done, waiting for you to merge) or needs-decision are skipped. To retry a blocked issue, answer on the issue
# and remove the `blocked` label: the next run continues on its branch.
#
# Settings (environment variables):
#   MODEL=opus          the model for Claude Code
#   AUTO_MERGE=1        merge each pull request when CI passes (0: leave it for you to merge)
#   MAX_ROUNDS=5        rounds per issue before it is marked blocked
#   WAIT_FOR_MORE=0     1: when nothing is ready, check again every 15 minutes instead of stopping
#   PERMISSION_MODE=auto
#
# Needs: Claude Code signed in, the GitHub CLI signed in (gh auth login), Docker Desktop, and a clean working tree.
# Keeps the Mac awake while it runs. Logs go to build-logs/. Stop it any time with Ctrl-C; run it again to carry on.
set -u
cd "$(dirname "$0")/.."
# Run from a copy, so that git pulling a newer version of this file while it runs cannot change it under bash's feet.
if [ -z "${RUN_ISSUES_COPY:-}" ]; then
  copy="$(mktemp -t run-issues.XXXXXX)"; cp "$0" "$copy"
  RUN_ISSUES_COPY=1 exec bash "$copy" "$@"
fi
REPO="${REPO:-jk2081/lifeos}"
MODEL="${MODEL:-opus}"; AUTO_MERGE="${AUTO_MERGE:-1}"; MAX_ROUNDS="${MAX_ROUNDS:-5}"
WAIT_FOR_MORE="${WAIT_FOR_MORE:-0}"; PERMISSION_MODE="${PERMISSION_MODE:-auto}"
LOG_DIR="build-logs"; mkdir -p "$LOG_DIR"

say() { echo "[$(date '+%d %b %H:%M')] $*" | tee -a "$LOG_DIR/issues.log"; }
notify() {
  say "$1"
  command -v osascript >/dev/null && osascript -e "display notification \"${1//\"/}\" with title \"Life OS build\"" >/dev/null 2>&1
  return 0
}

command -v claude >/dev/null || { echo "Claude Code is not installed."; exit 1; }
command -v gh >/dev/null || { echo "The GitHub CLI is not installed: brew install gh, then gh auth login."; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "The GitHub CLI is not signed in: gh auth login."; exit 1; }
command -v python3 >/dev/null || { echo "python3 is needed."; exit 1; }
if ! docker info >/dev/null 2>&1; then
  say "Docker is not running. Starting Docker Desktop."
  open -a Docker 2>/dev/null || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
  docker info >/dev/null 2>&1 || { say "Docker did not start. Open Docker Desktop and run this again."; exit 1; }
fi
docker start lifeos-db lifeos-redis lifeos-bench >/dev/null 2>&1 || true
[ -z "$(git status --porcelain)" ] || { echo "The working tree has changes. Commit or stash them first."; exit 1; }
if command -v caffeinate >/dev/null; then caffeinate -i -w $$ & fi
grep -qx '.issue/' .gitignore || { echo "The .issue/ line is missing from .gitignore."; exit 1; }

# The next issue to build: the lowest-numbered open `ready` issue that is not blocked or in progress and whose
# "Needs:" issues are all closed. Prints its number, or nothing.
next_issue() {
  gh issue list -R "$REPO" --state open --label ready --limit 200 --json number,labels,body | python3 -c '
import json, re, subprocess, sys
issues = sorted(json.load(sys.stdin), key=lambda i: i["number"])
skip = {"blocked", "in-progress", "in-review", "needs-decision"}
state = {}
def closed(n):
    if n not in state:
        out = subprocess.run(["gh", "issue", "view", str(n), "-R", sys.argv[1], "--json", "state", "-q", ".state"], capture_output=True, text=True)
        state[n] = out.stdout.strip() == "CLOSED"
    return state[n]
for i in issues:
    if skip & {l["name"] for l in i["labels"]}:
        continue
    m = re.search(r"\*\*Needs:\*\*([^\n]*)", i["body"] or "")
    needs = [int(x) for x in re.findall(r"#(\d+)", m.group(1))] if m else []
    if all(closed(n) for n in needs):
        print(i["number"]); break
' "$REPO"
}

# Wait for the pull request's checks. Returns 0 when they pass, 1 when they fail.
wait_for_ci() {
  local pr="$1"
  for _ in $(seq 1 20); do   # checks can take a minute to appear
    [ -n "$(gh pr checks "$pr" -R "$REPO" --json name -q '.[].name' 2>/dev/null)" ] && break
    sleep 15
  done
  gh pr checks "$pr" -R "$REPO" --watch --interval 60 >/dev/null 2>&1
}

save_ci_failure() {
  local branch="$1" run
  run=$(gh run list -R "$REPO" --branch "$branch" --status failure --limit 1 --json databaseId -q '.[0].databaseId')
  { echo "GitHub Actions failed on this branch (run $run). The failing steps' logs:"; echo
    gh run view "$run" -R "$REPO" --log-failed 2>&1 | tail -n 400; } > .issue/ci-failure.log
}

# A line every PROGRESS_EVERY seconds (default 600) while a round runs, so a quiet round is not mistaken for a hang.
progress() {
  local n="$1" round="$2" branch="$3" started="$4" commits latest editing
  while sleep "${PROGRESS_EVERY:-600}"; do
    commits=$(git rev-list --count "origin/main..$branch" 2>/dev/null || echo 0)
    latest=$(git log -1 --format='%s (%cr)' "$branch" 2>/dev/null | cut -c1-80)
    editing=$(git --no-optional-locks status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    say "Issue #$n, round $round: $(( ($(date +%s) - started) / 60 )) min in, $commits commits, $editing files being edited. Latest: $latest"
  done
}

prompt_for() {
  local n="$1" title="$2" branch="$3" round="$4"
  cat <<EOF
Nobody is watching this run. Do not ask questions and do not wait for input.

You are working on GitHub issue #$n, "$title", in $REPO, on the branch $branch. Read it with: gh issue view $n -R $REPO --comments
Follow docs/ISSUE_RULES.md exactly. Start the local stack as STATUS.md describes and check that the site and the tests work before changing anything.
EOF
  [ "$round" -gt 1 ] && echo "
This is round $round on this issue. Earlier rounds already did part of the work: read git log main..HEAD and continue from there."
  [ -f .issue/ci-failure.log ] && echo "
The pull request's GitHub Actions run failed. Read .issue/ci-failure.log, fix the cause on this branch, check the fix locally, and write .issue/result again."
  echo "
When the issue is finished or you cannot go further, write .issue/result (and .issue/pr.md or .issue/blocked.md) as docs/ISSUE_RULES.md says, then stop.
Do not stop, restart, remove or change any Docker container, image, volume or network whose name does not start with lifeos-."
}

mark_blocked() {
  local n="$1" branch="$2" why="$3"
  git push -q -u origin "$branch" 2>/dev/null
  gh issue comment "$n" -R "$REPO" --body "$(printf 'Blocked. Work so far is on the branch `%s`.\n\n%s' "$branch" "$why")" >/dev/null
  gh issue edit "$n" -R "$REPO" --add-label blocked --remove-label in-progress >/dev/null
  notify "Issue #$n is blocked. See the comment on the issue."
}

build_issue() {
  local n="$1" title slug branch round=1 started elapsed log pr result short=0
  title=$(gh issue view "$n" -R "$REPO" --json title -q .title)
  slug=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | cut -c1-40 | sed 's/-*$//')
  branch="issue-$n-$slug"
  gh issue edit "$n" -R "$REPO" --add-label in-progress >/dev/null
  git fetch -q origin
  git checkout -q main && git merge -q --ff-only origin/main
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    git checkout -q -B "$branch" "origin/$branch"
  else
    git checkout -q -B "$branch" origin/main
  fi
  rm -rf .issue && mkdir -p .issue
  notify "Started issue #$n: $title"
  ./scripts/get-frappe-skills.sh >/dev/null 2>&1 || say "Could not fetch the Frappe skills; using the copy in .claude/skills."

  while [ "$round" -le "$MAX_ROUNDS" ]; do
    log="$LOG_DIR/issue-$n-round-$round.log"
    say "Issue #$n, round $round"
    started=$(date +%s)
    progress "$n" "$round" "$branch" "$started" & PROGRESS=$!
    claude -p "$(prompt_for "$n" "$title" "$branch" "$round")" --model "$MODEL" --permission-mode "$PERMISSION_MODE" --verbose > "$log" 2>&1
    kill "$PROGRESS" 2>/dev/null
    elapsed=$(( $(date +%s) - started ))
    say "Round $round ended after $((elapsed / 60)) minutes."
    [ "$(git branch --show-current)" = "$branch" ] || git checkout -q "$branch"
    if [ -n "$(git status --porcelain)" ]; then git add -A && git commit -q -m "#$n: work in progress saved by the runner"; fi
    git push -q -u origin "$branch" 2>>"$LOG_DIR/issues.log" || say "Push failed; the work is committed locally."

    # A very short round without a result is usually a usage limit: wait and try again without counting the round.
    if [ "$elapsed" -lt 240 ] && [ ! -f .issue/result ]; then
      tail -n 3 "$log" | tee -a "$LOG_DIR/issues.log"
      short=$((short + 1))
      if [ "$short" -ge 6 ]; then
        notify "Six short rounds in a row on issue #$n. Check that Claude Code is signed in, then run this again."
        gh issue edit "$n" -R "$REPO" --remove-label in-progress >/dev/null
        exit 1
      fi
      say "Short round with no result, probably a usage limit. Waiting 30 minutes."
      sleep 1800; continue
    fi
    short=0

    result=$(tr -d '[:space:]' < .issue/result 2>/dev/null || true)
    if [ "$result" = "blocked" ]; then
      mark_blocked "$n" "$branch" "$(cat .issue/blocked.md 2>/dev/null || echo 'No reason was written.')"
      return
    fi
    if [ "$result" = "done" ]; then
      pr=$(gh pr list -R "$REPO" --head "$branch" --state open --json number -q '.[0].number')
      [ -f .issue/pr.md ] || printf 'Closes #%s\n' "$n" > .issue/pr.md
      grep -q "Closes #$n" .issue/pr.md || printf '\nCloses #%s\n' "$n" >> .issue/pr.md
      if [ -z "$pr" ]; then
        gh pr create -R "$REPO" --base main --head "$branch" --title "#$n: $title" --body-file .issue/pr.md >/dev/null
        pr=$(gh pr list -R "$REPO" --head "$branch" --state open --json number -q '.[0].number')
        notify "Pull request #$pr opened for issue #$n."
      else
        gh pr edit "$pr" -R "$REPO" --body-file .issue/pr.md >/dev/null
      fi
      say "Waiting for GitHub Actions on pull request #$pr."
      if wait_for_ci "$pr"; then
        rm -f .issue/ci-failure.log
        if [ "$AUTO_MERGE" = "1" ]; then
          if gh pr merge "$pr" -R "$REPO" --squash --delete-branch >/dev/null 2>&1; then
            notify "Issue #$n done: pull request #$pr merged."
          else
            gh issue edit "$n" -R "$REPO" --add-label in-review >/dev/null
            notify "Issue #$n done, but pull request #$pr could not be merged. Merge it on GitHub."
          fi
        else
          gh issue edit "$n" -R "$REPO" --add-label in-review >/dev/null
          notify "Issue #$n done: pull request #$pr passed CI and is waiting for you."
        fi
        gh issue edit "$n" -R "$REPO" --remove-label in-progress >/dev/null
        return
      fi
      say "CI failed on pull request #$pr. Sending the failure back to Claude."
      save_ci_failure "$branch"
      rm -f .issue/result
    fi
    round=$((round + 1))
  done
  mark_blocked "$n" "$branch" "Not finished after $MAX_ROUNDS rounds. The round logs are in build-logs/ on the Mac that ran it."
}

say "Runner started. Model: $MODEL. Auto-merge: $AUTO_MERGE. Up to $MAX_ROUNDS rounds per issue."
trap 'git checkout -q main 2>/dev/null; say "Runner stopped."' EXIT

if [ "$#" -gt 0 ]; then
  for n in "$@"; do build_issue "$n"; git checkout -q main; done
  exit 0
fi

done_count=0
while true; do
  n=$(next_issue)
  if [ -z "$n" ]; then
    if [ "$WAIT_FOR_MORE" = "1" ]; then sleep 900; continue; fi
    notify "Nothing left that is ready. $done_count issues worked on in this run."
    break
  fi
  build_issue "$n"
  git checkout -q main
  done_count=$((done_count + 1))
done
