# Life OS

A personal operating system on Frappe: inbox and review, tasks, calendar, a journal that mirrors a paper journal, areas and projects, a vault, and a chat log. Agents capture and propose; the owner approves.

## What is here

| Path | What it is |
| --- | --- |
| `SPEC.md` | The v1 build spec |
| `mockups/` | Approved screen mockups as PNG, with their HTML source |
| `CLAUDE.md` | Standing instructions for a coding agent working in this repo |
| `START_PROMPT.md`, `CONTINUE_PROMPT.md` | The prompts the build script sends |
| `scripts/start-build.sh` | Starts and supervises an unattended build |

## Start the build

On a Mac with Docker Desktop and Claude Code installed:

```
git clone https://github.com/jk2081/lifeos.git
cd lifeos
./scripts/start-build.sh
```

The script keeps the Mac awake, runs Claude Code without prompts in auto permission mode, restarts it if a run ends early, commits after every round and pushes to GitHub. It stops when the build writes `BUILD_DONE` or `BUILD_BLOCKED`, or after 12 rounds.

- Progress: `STATUS.md`, `git log`, and `build-logs/build.log`.
- To continue a stopped build, run the script again.
- To use another model or permission mode: `MODEL=opus PERMISSION_MODE=acceptEdits ./scripts/start-build.sh`.

The app does not exist yet. Install steps for an existing bench will be written to `STATUS.md` by the build.

### Using an existing bench instead of Docker

```
BENCH_PATH=~/frappe-bench ./scripts/start-build.sh
```

The build then creates one new site, `lifeos.localhost`, on that bench and is told not to touch other sites, run `bench update`, or change other apps. The bench must be Frappe v16. Docker is the safer choice, because the build cannot affect anything else.
