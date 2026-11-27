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

## The bench cache (CI)

Building Frappe's bench takes about 25 minutes, so CI restores it from a cache instead. The Frappe release is written once, in `.github/frappe-version`; the cache keys (`frappe-bench-tests-…` for the unit job, `frappe-bench-walk-…` for the walks, made by `.github/actions/bench-cache`) and the bench setup (`tools/ci-bench.sh`) both read it.

- **Only a cache saved on `main` is shared with every pull request** (one saved on a branch is that branch's alone). So `cache-bench.yml` builds and saves both benches on main: on a push that changes the Frappe version, the action, `tools/ci-bench.sh` or `pyproject.toml`; every Sunday (GitHub drops a cache unused for 7 days); and by hand. It has its own concurrency group that never cancels, so a later push to main cannot stop it. `ci.yml` only restores.
- **Every job says** `bench cache: hit (key …)` or `bench cache: miss: building (key …)` in its log and step summary; on a pull request a miss also raises a warning annotation. A miss builds the bench and carries on; it is slow, not a failure.
- **When the Frappe version changes:** edit `.github/frappe-version` and merge. The push to main runs `cache-bench.yml` and saves the new keys. Until it finishes, pull requests miss and build. To rebuild without a change (a cache evicted), run "Cache the bench" by hand from the Actions tab on `main`. To force a fresh bench under the same version, bump the `-1` at the end of the key in `.github/actions/bench-cache/action.yml`.

## The guards (so the cleanup stays done)

Each guard fails CI on a **new** finding, against a baseline that only shrinks (a baseline entry that no longer applies also fails, so it is taken out). They need no bench, so the `guards` job in `ci.yml` runs them on every pull request, the `quick` lane included. Each has its own acceptance check, `CORE.5` to `CORE.9`.

| Guard | Catches | Run | An allowed exception goes in |
| --- | --- | --- | --- |
| G0 `tools/guard-routes.mjs` | a `.vue` file that links straight to a record's page instead of opening it in the Drawer | `node tools/guard-routes.mjs` | a `guard-allow` comment on that line (the Library's own tree), or `ALLOWED` in the guard (the Drawer's own panes) |
| G1 `tools/guard-api.py` | an `@frappe.whitelist` method that no screen, test, other file or skill calls (a screen's `api('ns.name')`, the data layer's `group('ns', [...])`, a dotted path or a quoted name all count) | `python3 -I tools/guard-api.py` | `tools/guard-api-allow.json`: `{ "lifeos.api.x.name": "one line on why it is called only at run time" }`. An entry that becomes used fails, so it is removed |
| G2 `tools/guard-dup.mjs` | copy-paste: jscpd over `frontend/src` and `lifeos/` above the share stored in `tools/guard-dup-ceiling.json` (the level after the cleanup; lower it when a run is clearly below, never raise it) | `node tools/guard-dup.mjs`; `--measure` prints the levels | no allow list: share the code |
| G3 `tools/guard-ui.mjs` | a raw `<button>`, `<select>`, `<input>` or `<textarea>` in a `.vue` file outside `components/ui/` (the whole-row `<button class="absolute inset-0">` and `<input type="file">` stay). `frontend/scripts/check-sfc.mjs` uses the same function | `node tools/guard-ui.mjs` | none: use the frappe-ui control, or make the part in `components/ui/` |
| G4 `tools/guard-ui.mjs` | a file in `components/ui/` that `frontend/COMPONENTS.md` does not list; in a file not in the baseline, a hand-built list row (a `v-for` element with a border class and no `Row`) or section heading (`<h2>`/`<h3>` outside a page header or dialog) | `node tools/guard-ui.mjs` | `tools/guard-ui-baseline.json`: the files that still build a row or heading by hand (screen and step titles, calendar grids). A new file does not go in it; an entry is deleted when its file is clean |

**The monthly check.** `.github/workflows/monthly-cleanup.yml` runs on the 1st of each month (or by hand from the Actions tab). `tools/monthly-cleanup.mjs` runs the guards in report mode, jscpd and vulture over `lifeos/`, and opens **one** issue "Monthly cleanup check: <month>" labelled `audit`, never `ready`. With no findings it opens nothing, and a second run in the same month opens no second issue. Read it, and turn what is worth doing into issues labelled `ready`.
