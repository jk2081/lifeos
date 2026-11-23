# How Life OS gets built

## The loop

1. **Backlog.** Every piece of work is a GitHub issue with acceptance tests. Issues labelled `ready` are built, lowest number first. An issue that says `**Needs:** #a` waits until #a is closed.
2. **Runner.** `./scripts/run-issues.sh` on the Mac picks the next ready issue and runs Claude Code (Opus) on it in rounds until it is done or blocked. Issues are built in **batches of three** on one branch, each with its own commits and its own local tests.
3. **Pull request.** A full batch becomes one pull request that closes its three issues. While GitHub tests it, the next batch is already being built on top of it, so nothing waits.
4. **CI.** GitHub Actions runs the full unit suite, the scan and the acceptance walk (`tools/acceptance.mjs`, one job per place side by side: Today, Brain, Goals, Library, Review, Settings, Phone and the tooling) on the pull request (`.github/workflows/ci.yml`). A failed walk uploads its screenshots and logs as an artifact of the run. If CI fails, the runner stops between issues, has Claude fix that batch, and carries the fix into the batch in progress.
   - **Tests on the Mac stay short.** The whole acceptance walk runs only on GitHub: on the Mac it refuses to start under the runner. A fix round reruns only the checks that failed (`--only=`). A round in which no file or commit changes for 20 minutes (`QUIET_LIMIT`), almost always a long test run, is stopped; its work is committed and pushed, and GitHub tests it.
5. **Merge.** When CI is green, the runner merges (a merge commit, so stacked batches stay clean) and the issues close. Set `AUTO_MERGE=0` to merge yourself; `BATCH_SIZE=1` goes back to one pull request per issue.
6. **Deploy.** This stays manual: on the server, pull, migrate, build, restart. Later, bench_updater (#2) will do it.

## Starting it

On the Mac, once:

```
brew install gh && gh auth login        # sign in to GitHub
cd ~/Code/lifeos && git pull
```

Then, each time:

```
./scripts/run-issues.sh                 # every ready issue, until none are left
./scripts/run-issues.sh 4 5             # only these issues
AUTO_MERGE=0 ./scripts/run-issues.sh    # leave each pull request for you to merge
```

The Mac must stay on and awake, with Docker Desktop running; the script keeps it awake while it runs. Closing the lid sleeps it, unless an external display and power are connected. Ctrl-C stops the runner, and running it again carries on: an issue's branch is kept on GitHub.

## Following it from the phone

- GitHub notifies you of every pull request, merge and blocked issue. Watch the repo in the GitHub app.
- The Mac shows a notification at each step. `build-logs/issues.log` has one line per step.

## Labels

| Label | Meaning |
| --- | --- |
| `ready` | Agreed; the runner may build it |
| `in-progress` | The runner is on it |
| `in-review` | Done and green; waiting for you to merge (only when the merge did not happen) |
| `blocked` | The runner stopped; the issue's last comment says why. Answer on the issue and remove the label to retry |
| `needs-decision` | Waiting for a decision from you before it can be built |
| `phase-1` … `phase-4` | Order of the plan |

## Writing an issue

Title: what changes, in plain words. Body:

- **Needs:** the issues that must be closed first, or "nothing".
- **Mockups:** the boards in `mockups/v2/` to match, if any.
- **What to build.**
- **Acceptance tests:** numbered, each one checkable by a test. They become `I<n>.<k>` checks or unit tests.
- **Not in this issue.**

The rules every issue follows are in `docs/ISSUE_RULES.md`; the target design is in `docs/DIRECTION.md`.
