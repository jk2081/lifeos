#!/bin/bash
# Work through the GitHub issues labelled `ready`, unattended, until none are left.
#
#   ./scripts/run-issues.sh          every open `ready` issue, lowest number first
#   ./scripts/run-issues.sh 12 15    only these issues, in this order
#
# Issues are built in batches (BATCH_SIZE, default 3) on one branch, one after another, each with its own commits and its
# own local tests (docs/ISSUE_RULES.md). A full batch becomes one pull request that closes its issues, so GitHub Actions
# runs once per batch, not once per issue. While GitHub tests a batch, the next batch is already being built on a branch
# that starts from it. When the tests pass, the pull request is merged and its issues close. When they fail, the runner
# stops between issues, has Claude fix that batch on its own branch, and carries the fix into the batch in progress.
#
# A blocked issue gets a comment and the `blocked` label; its work is kept on its own branch (issue-<n>-blocked) and
# taken out of the batch, so it never holds up the others. An issue whose body says "**Needs:** #a, #b" waits until
# those issues are closed or done in a batch before it. Issues labelled blocked, in-progress, in-review or
# needs-decision are skipped. To retry a blocked issue, answer on the issue and remove the `blocked` label.
#
# Settings (environment variables):
#   MODEL=opus          the model for Claude Code
#   BATCH_SIZE=3        issues per pull request (1: one pull request per issue, as before)
#   AUTO_MERGE=1        merge each pull request when CI passes (0: leave it for you; the next batch waits for your merge)
#   MAX_ROUNDS=5        rounds per issue before it is marked blocked
#   WAIT_FOR_MORE=0     1: when nothing is ready, check again every 15 minutes instead of stopping
#   PERMISSION_MODE=auto
#
# Needs: Claude Code signed in, the GitHub CLI signed in (gh auth login), Docker Desktop, and a clean working tree.
# Keeps the Mac awake while it runs. Logs go to build-logs/. Stop it with Ctrl-C between issues and run it again to
# carry on: where it was is kept in .git/run-issues.state.
set -u
# Run from a copy, so that git pulling a newer version of this file while it runs cannot change it under bash's feet.
# The copy lives in a temporary folder, so the repo's folder is passed along.
if [ -z "${RUN_ISSUES_ROOT:-}" ]; then
  RUN_ISSUES_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  copy="$(mktemp -t run-issues.XXXXXX)"; cp "$0" "$copy"
  RUN_ISSUES_ROOT="$RUN_ISSUES_ROOT" exec bash "$copy" "$@"
fi
cd "$RUN_ISSUES_ROOT"
REPO="${REPO:-jk2081/lifeos}"
MODEL="${MODEL:-opus}"; AUTO_MERGE="${AUTO_MERGE:-1}"; MAX_ROUNDS="${MAX_ROUNDS:-5}"; BATCH_SIZE="${BATCH_SIZE:-3}"
WAIT_FOR_MORE="${WAIT_FOR_MORE:-0}"; PERMISSION_MODE="${PERMISSION_MODE:-auto}"
LOG_DIR="build-logs"; mkdir -p "$LOG_DIR"
STATE=".git/run-issues.state"

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

# ---- state: the batch being built, and the batch whose pull request GitHub is testing ----
BATCH_BRANCH=""; BATCH_ISSUES=""      # issues done on the batch being built, space-separated
PENDING_PR=""; PENDING_BRANCH=""; PENDING_ISSUES=""
[ -f "$STATE" ] && . "$STATE"
save_state() {
  printf 'BATCH_BRANCH=%q\nBATCH_ISSUES=%q\nPENDING_PR=%q\nPENDING_BRANCH=%q\nPENDING_ISSUES=%q\n' \
    "$BATCH_BRANCH" "$BATCH_ISSUES" "$PENDING_PR" "$PENDING_BRANCH" "$PENDING_ISSUES" > "$STATE"
}
count() { set -- $1; echo $#; }
hashes() { local s=""; for n in $1; do s="$s #$n"; done; echo "${s# }"; }

# The next issue to build: the lowest-numbered open `ready` issue that is not skipped and whose "Needs:" issues are
# closed or already done in a batch. Prints its number, or nothing.
next_issue() {
  gh issue list -R "$REPO" --state open --label ready --limit 200 --json number,labels,body | python3 -c '
import json, re, subprocess, sys
issues = sorted(json.load(sys.stdin), key=lambda i: i["number"])
done_here = {int(x) for x in sys.argv[2].split()}
skip = {"blocked", "in-progress", "in-review", "needs-decision"}
state = {}
def closed(n):
    if n in done_here:
        return True
    if n not in state:
        out = subprocess.run(["gh", "issue", "view", str(n), "-R", sys.argv[1], "--json", "state", "-q", ".state"], capture_output=True, text=True)
        state[n] = out.stdout.strip() == "CLOSED"
    return state[n]
for i in issues:
    if i["number"] in done_here or skip & {l["name"] for l in i["labels"]}:
        continue
    m = re.search(r"\*\*Needs:\*\*([^\n]*)", i["body"] or "")
    needs = [int(x) for x in re.findall(r"#(\d+)", m.group(1))] if m else []
    if all(closed(n) for n in needs):
        print(i["number"]); break
' "$REPO" "$BATCH_ISSUES $PENDING_ISSUES"
}

# The state of a pull request's checks: pass, fail or pending.
ci_state() {
  local pr="$1" out
  out=$(gh pr checks "$pr" -R "$REPO" --json bucket -q '.[].bucket' 2>/dev/null)
  if [ -z "$out" ]; then echo pending
  elif echo "$out" | grep -qE 'fail|cancel'; then echo fail
  elif echo "$out" | grep -q pending; then echo pending
  else echo pass; fi
}
wait_ci() {   # blocks until the checks finish; prints pass or fail
  local pr="$1" s
  while true; do s=$(ci_state "$pr"); [ "$s" != pending ] && { echo "$s"; return; }; sleep 60; done
}

save_ci_failure() {
  local branch="$1" run
  run=$(gh run list -R "$REPO" --branch "$branch" --status failure --limit 1 --json databaseId -q '.[0].databaseId')
  { echo "GitHub Actions failed on this branch (run $run). The failing steps' logs:"; echo
    gh run view "$run" -R "$REPO" --log-failed 2>&1 | tail -n 400; } > .issue/ci-failure.log
}

# A line every PROGRESS_EVERY seconds (default 600) while a round runs, so a quiet round is not mistaken for a hang.
progress() {
  local what="$1" round="$2" branch="$3" started="$4" latest editing
  while sleep "${PROGRESS_EVERY:-600}"; do
    latest=$(git log -1 --format='%s (%cr)' "$branch" 2>/dev/null | cut -c1-80)
    editing=$(git --no-optional-locks status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    say "$what, round $round: $(( ($(date +%s) - started) / 60 )) min in, $editing files being edited. Latest commit: $latest"
  done
}

issue_prompt() {
  local n="$1" title="$2" branch="$3" round="$4"
  cat <<EOF
Nobody is watching this run. Do not ask questions and do not wait for input.

You are working on GitHub issue #$n, "$title", in $REPO, on the branch $branch. Read it with: gh issue view $n -R $REPO --comments
This branch is a batch: it may already hold other finished issues (see git log origin/main..HEAD). Leave their work as it is.
Follow docs/ISSUE_RULES.md exactly, except that the runner, not you, opens the pull request. Start the local stack as STATUS.md describes and check that the site and the tests work before changing anything.
EOF
  [ "$round" -gt 1 ] && echo "
This is round $round on this issue. Earlier rounds already did part of the work: read the commits starting \"#$n:\" and continue from there."
  echo "
When the issue is finished or you cannot go further, write .issue/result (and .issue/pr.md or .issue/blocked.md) as docs/ISSUE_RULES.md says, then stop. .issue/pr.md is this issue's part of the batch's pull request text.
Do not stop, restart, remove or change any Docker container, image, volume or network whose name does not start with lifeos-."
}

fix_prompt() {
  local pr="$1" branch="$2" issues="$3"
  cat <<EOF
Nobody is watching this run. Do not ask questions and do not wait for input.

Pull request #$pr in $REPO, on the branch $branch, holds the work for issues $(hashes "$issues"). Its GitHub Actions run failed.
Read .issue/ci-failure.log, find the cause, fix it on this branch with commits starting "CI fix:", and check the fix locally (the failing tests, then the unit suite). Follow docs/ISSUE_RULES.md. Start the local stack as STATUS.md describes first.
When the fix is in, write the single word done to .issue/result. If you cannot fix it, write blocked to .issue/result and the reason to .issue/blocked.md. Then stop.
Do not stop, restart, remove or change any Docker container, image, volume or network whose name does not start with lifeos-.
EOF
}

# Run Claude in rounds until .issue/result exists. Waits out usage limits. Returns 0 on done, 1 on blocked or too many rounds.
run_rounds() {
  local what="$1" branch="$2" prompt_fn="$3"; shift 3
  local round=1 started elapsed log short=0 result
  while [ "$round" -le "$MAX_ROUNDS" ]; do
    log="$LOG_DIR/$(echo "$what" | tr -cs 'A-Za-z0-9' '-')round-$round.log"
    say "$what, round $round"
    started=$(date +%s)
    progress "$what" "$round" "$branch" "$started" & local PROGRESS=$!
    claude -p "$("$prompt_fn" "$@" "$round")" --model "$MODEL" --permission-mode "$PERMISSION_MODE" --verbose > "$log" 2>&1
    pkill -P "$PROGRESS" 2>/dev/null; kill "$PROGRESS" 2>/dev/null
    elapsed=$(( $(date +%s) - started ))
    say "Round $round ended after $((elapsed / 60)) minutes."
    [ "$(git branch --show-current)" = "$branch" ] || git checkout -q "$branch"
    if [ -n "$(git status --porcelain)" ]; then git add -A && git commit -q -m "$what: work in progress saved by the runner"; fi
    git push -q -u origin "$branch" 2>>"$LOG_DIR/issues.log" || say "Push failed; the work is committed locally."
    if [ "$elapsed" -lt 240 ] && [ ! -f .issue/result ]; then   # a usage limit, usually
      tail -n 3 "$log" | tee -a "$LOG_DIR/issues.log"
      short=$((short + 1))
      [ "$short" -ge 6 ] && { notify "Six short rounds in a row. Check that Claude Code is signed in, then run this again."; exit 1; }
      say "Short round with no result, probably a usage limit. Waiting 30 minutes."
      sleep 1800; continue
    fi
    short=0
    result=$(tr -d '[:space:]' < .issue/result 2>/dev/null || true)
    [ "$result" = done ] && return 0
    [ "$result" = blocked ] && return 1
    round=$((round + 1))
  done
  echo "Not finished after $MAX_ROUNDS rounds. The round logs are in build-logs/ on the Mac that ran it." > .issue/blocked.md
  return 1
}
fix_prompt_r() { fix_prompt "$1" "$2" "$3"; }   # the round number is not needed for a fix
issue_prompt_r() { issue_prompt "$@"; }

# ---- the batch whose pull request is being tested ----
merge_pending() {
  if [ "$AUTO_MERGE" = 1 ] && gh pr merge "$PENDING_PR" -R "$REPO" --merge --delete-branch >/dev/null 2>&1; then
    for n in $PENDING_ISSUES; do
      gh issue close "$n" -R "$REPO" --reason completed >/dev/null 2>&1 || true
      gh issue edit "$n" -R "$REPO" --remove-label in-review >/dev/null 2>&1 || true
    done
    notify "Merged pull request #$PENDING_PR: $(hashes "$PENDING_ISSUES") done."
  else
    notify "Pull request #$PENDING_PR ($(hashes "$PENDING_ISSUES")) passed CI and is waiting for you to merge it."
    while [ "$(gh pr view "$PENDING_PR" -R "$REPO" --json state -q .state)" != MERGED ]; do sleep 300; done
    for n in $PENDING_ISSUES; do gh issue edit "$n" -R "$REPO" --remove-label in-review >/dev/null 2>&1 || true; done
    say "Pull request #$PENDING_PR was merged."
  fi
  PENDING_PR=""; PENDING_BRANCH=""; PENDING_ISSUES=""; save_state
  git fetch -q origin
}

# Fix a failed batch on its own branch, wait for CI again, then carry the fix into the batch being built.
fix_pending() {
  local tries=0
  while [ "$tries" -lt 3 ]; do
    tries=$((tries + 1))
    notify "CI failed on pull request #$PENDING_PR. Fixing it (try $tries)."
    git checkout -q "$PENDING_BRANCH"
    rm -rf .issue && mkdir -p .issue && save_ci_failure "$PENDING_BRANCH"
    local before_fix; before_fix=$(git rev-parse HEAD)
    if ! run_rounds "CI fix for #$PENDING_PR" "$PENDING_BRANCH" fix_prompt_r "$PENDING_PR" "$PENDING_BRANCH" "$PENDING_ISSUES"; then
      break
    fi
    # A fix that changed nothing cannot pass: say so instead of re-reading the same failed checks.
    if [ "$(git rev-parse HEAD)" = "$before_fix" ]; then
      echo "The fix round made no change, so the same checks would fail again." > .issue/blocked.md
      continue
    fi
    sleep 60   # let GitHub register the new commit's checks before reading them
    if [ "$(wait_ci "$PENDING_PR")" = pass ]; then
      local fixed="$PENDING_BRANCH"
      merge_pending
      if [ -n "$BATCH_BRANCH" ]; then
        git checkout -q "$BATCH_BRANCH"
        if ! git merge -q --no-edit "origin/main" 2>/dev/null; then
          git merge --abort 2>/dev/null
          notify "The CI fix on $fixed clashes with the batch in progress ($BATCH_BRANCH). Merge main into it by hand, then run this again."
          exit 1
        fi
        git push -q origin "$BATCH_BRANCH" 2>/dev/null
      fi
      return 0
    fi
  done
  for n in $PENDING_ISSUES; do
    gh issue edit "$n" -R "$REPO" --add-label blocked --remove-label in-review >/dev/null 2>&1
  done
  gh pr comment "$PENDING_PR" -R "$REPO" --body "CI still fails after the runner's fixes. $(cat .issue/blocked.md 2>/dev/null)" >/dev/null 2>&1
  notify "Pull request #$PENDING_PR still fails CI. Its issues are marked blocked; the runner stops so nothing builds on top of it."
  exit 1
}

# Called between issues: merge the tested batch if it passed, fix it if it failed, or do nothing if still running.
check_pending() {
  [ -z "$PENDING_PR" ] && return 0
  case "$(ci_state "$PENDING_PR")" in
    pass) merge_pending ;;
    fail) fix_pending ;;
  esac
}
wait_pending() {   # before opening the next pull request: the one before it must be merged first
  [ -z "$PENDING_PR" ] && return 0
  say "Waiting for GitHub Actions on pull request #$PENDING_PR before opening the next one."
  if [ "$(wait_ci "$PENDING_PR")" = pass ]; then merge_pending; else fix_pending; fi
}

# ---- the batch being built ----
start_batch() {
  local first="$1"
  BATCH_BRANCH="batch-$first"; BATCH_ISSUES=""
  git fetch -q origin
  local base="origin/main"
  [ -n "$PENDING_BRANCH" ] && base="$PENDING_BRANCH"   # build on top of the batch being tested
  if git ls-remote --exit-code --heads origin "$BATCH_BRANCH" >/dev/null 2>&1; then
    git checkout -q -B "$BATCH_BRANCH" "origin/$BATCH_BRANCH"
  else
    git checkout -q -B "$BATCH_BRANCH" "$base"
  fi
  save_state
}

open_batch_pr() {
  [ -z "$BATCH_ISSUES" ] && return 0
  wait_pending
  git checkout -q "$BATCH_BRANCH"
  if ! git merge -q --no-edit origin/main 2>/dev/null; then
    git merge --abort 2>/dev/null
    notify "$BATCH_BRANCH clashes with main. Merge main into it by hand, then run this again."
    exit 1
  fi
  git push -q -u origin "$BATCH_BRANCH" 2>>"$LOG_DIR/issues.log"
  local body="$LOG_DIR/pr-$BATCH_BRANCH.md" titles="" n
  {
    echo "Built by \`scripts/run-issues.sh\`: $(count "$BATCH_ISSUES") issues, each with its own commits and local tests."; echo
    for n in $BATCH_ISSUES; do
      echo "## #$n: $(gh issue view "$n" -R "$REPO" --json title -q .title)"; echo
      cat "$LOG_DIR/pr-part-$n.md" 2>/dev/null | grep -v '^Closes #'; echo
    done
    for n in $BATCH_ISSUES; do echo "Closes #$n"; done
  } > "$body"
  for n in $BATCH_ISSUES; do titles="$titles, #$n"; done
  gh pr create -R "$REPO" --base main --head "$BATCH_BRANCH" --title "Issues ${titles#, }" --body-file "$body" >/dev/null
  PENDING_PR=$(gh pr list -R "$REPO" --head "$BATCH_BRANCH" --state open --json number -q '.[0].number')
  PENDING_BRANCH="$BATCH_BRANCH"; PENDING_ISSUES="$BATCH_ISSUES"
  BATCH_BRANCH=""; BATCH_ISSUES=""
  save_state
  notify "Pull request #$PENDING_PR opened for $(hashes "$PENDING_ISSUES"). GitHub is testing it; the next batch starts now."
}

build_issue() {
  local n="$1" title before
  if [ "$(gh issue view "$n" -R "$REPO" --json state -q .state)" = "CLOSED" ]; then say "Issue #$n is already closed. Skipping it."; return; fi
  title=$(gh issue view "$n" -R "$REPO" --json title -q .title)
  [ -z "$BATCH_BRANCH" ] && start_batch "$n"
  git checkout -q "$BATCH_BRANCH"
  before=$(git rev-parse HEAD)
  gh issue edit "$n" -R "$REPO" --add-label in-progress >/dev/null
  rm -rf .issue && mkdir -p .issue
  notify "Started issue #$n: $title (batch $BATCH_BRANCH)"
  ./scripts/get-frappe-skills.sh >/dev/null 2>&1 || say "Could not fetch the Frappe skills; using the copy in .claude/skills."
  if run_rounds "Issue #$n" "$BATCH_BRANCH" issue_prompt_r "$n" "$title" "$BATCH_BRANCH"; then
    cp .issue/pr.md "$LOG_DIR/pr-part-$n.md" 2>/dev/null || echo "" > "$LOG_DIR/pr-part-$n.md"
    BATCH_ISSUES="${BATCH_ISSUES:+$BATCH_ISSUES }$n"; save_state
    gh issue edit "$n" -R "$REPO" --add-label in-review --remove-label in-progress >/dev/null
    notify "Issue #$n done ($(count "$BATCH_ISSUES") of $BATCH_SIZE in this batch)."
  else
    # Keep the blocked work on its own branch and take it out of the batch.
    git branch -f "issue-$n-blocked" HEAD && git push -q -f origin "issue-$n-blocked" 2>/dev/null
    git reset -q --hard "$before" && git push -q -f origin "$BATCH_BRANCH" 2>/dev/null
    gh issue comment "$n" -R "$REPO" --body "$(printf 'Blocked. Work so far is on the branch `issue-%s-blocked`.\n\n%s' "$n" "$(cat .issue/blocked.md 2>/dev/null || echo 'No reason was written.')")" >/dev/null
    gh issue edit "$n" -R "$REPO" --add-label blocked --remove-label in-progress >/dev/null
    notify "Issue #$n is blocked. See the comment on the issue. The batch carries on without it."
  fi
}

say "Runner started. Model: $MODEL. Batches of $BATCH_SIZE. Auto-merge: $AUTO_MERGE. Up to $MAX_ROUNDS rounds per issue."
[ -n "$PENDING_PR$BATCH_BRANCH" ] && say "Carrying on: pull request ${PENDING_PR:-none} being tested ($(hashes "$PENDING_ISSUES")), batch ${BATCH_BRANCH:-none} ($(hashes "$BATCH_ISSUES"))."
trap 'say "Runner stopped."' EXIT
# Only one runner works at a time, so an `in-progress` label left by a stopped run is stale: clear it, and the issue
# is picked up again (its earlier commits, if any, are still on the batch branch).
for n in $(gh issue list -R "$REPO" --state open --label in-progress --json number -q '.[].number'); do
  gh issue edit "$n" -R "$REPO" --remove-label in-progress >/dev/null && say "Cleared a stale in-progress label on #$n."
done
[ -n "$BATCH_BRANCH" ] && git checkout -q "$BATCH_BRANCH" 2>/dev/null

queue=("$@")
done_count=0
while true; do
  check_pending
  if [ "${#queue[@]}" -gt 0 ]; then n="${queue[0]}"; queue=("${queue[@]:1}"); elif [ "$#" -gt 0 ]; then n=""; else n=$(next_issue); fi
  if [ -z "$n" ]; then
    open_batch_pr
    wait_pending
    if [ "$WAIT_FOR_MORE" = 1 ] && [ "$#" -eq 0 ]; then sleep 900; continue; fi
    rm -f "$STATE"
    git checkout -q main && git merge -q --ff-only origin/main 2>/dev/null
    notify "Nothing left that is ready. $done_count issues worked on in this run."
    break
  fi
  build_issue "$n"
  done_count=$((done_count + 1))
  [ "$(count "$BATCH_ISSUES")" -ge "$BATCH_SIZE" ] && open_batch_pr
done
