# The Life OS connector

A small skill and a script your agent runs beside itself. Nothing in the agent's own code changes.

What it does, each time it runs (every 15 minutes and once a day in full):

1. **Picks up** what you changed in Life OS (`lifeos.api.agent_connector.pull`): a fact you edited or deleted, a job you paused or resumed, a switch under "What it can do", and your answer to anything the agent asked to do.
2. **Applies** each change to the agent's own files. One it cannot apply is *failed*, with the reason, on the agent's page.
3. **Reports** what the agent holds now (`lifeos.api.agent_connector.report`): its memory, skills, jobs, settings and what it did this week. Life OS keeps exactly that. A report that repeats the last one changes nothing.
4. **Confirms** (`lifeos.api.agent_connector.confirm`) what it applied or could not, and which of your answers it has picked up. Until then the page shows each change as *waiting*; after, *applied* or *failed*.

## Set it up on the agent's server

1. In Life OS, give the agent an API key: Settings, People and agents, add the agent as a member with the role Life Agent, then create an API key for that user. Put the key and secret in the environment of the agent's server, never in a file in this repository:

       export LIFEOS_URL=https://your-life-os
       export LIFEOS_API_KEY=...
       export LIFEOS_API_SECRET=...

2. Copy `connector.py` and `SKILL.md` to the agent's server. `SKILL.md` is the skill that tells the agent to keep the files below up to date and to ask before it sends, moves or chases anything.
3. Point the connector at the folder where the agent keeps its files, and say what Life OS should call it (its `source_system`, for example `my-agent`):

       python3 connector.py --home /path/to/agent/files --system my-agent --space "My Space"

   Add `--loop` to keep it running, or run it from cron.
4. Open Brain, Sources: the agent is there under the name you give it (it starts as "Your assistant").

## The agent's files

All are in the `--home` folder. A missing file is an empty list.

| File | Holds |
| --- | --- |
| `memory.json` | `[{"id": "f1", "text": "Prefers mornings for calls", "origin": "WhatsApp, 1 Nov", "learned_on": "2026-11-01"}]` (without an `id`, one is made from the text) |
| `jobs.json` | `[{"id": "j1", "name": "Morning digest", "schedule": "Every day 7:00", "next_run": "tomorrow 7:00", "paused": false}]` |
| `skills/<name>/SKILL.md` | one folder for each skill; the first line of text is its description |
| `settings.json` | `{"abilities": {"send_email": "ask", "read_email": "auto", "pay": "off"}}`; each is `auto` (on its own), `ask` (asks you) or `off`. Pay is always off |
| `actions.json` | `[{"id": "a1", "action": "send_email", "title": "Chase Mehi Motors", "draft": "...", "status": "Waiting", "cost": 0.01, "when": "2026-11-23 10:00"}]`. `Waiting` is something it will not do until you approve; `Done` is something it did |

If the agent keeps its files another way, change `snapshot` and `apply_change` in `connector.py`: they are the only two places that know the layout.

## What Life OS does with it

- An area you switch off on the agent's page is left out of everything the agent reads from Life OS, whatever the agent asks for. The Vault is always off. Paying is always off.
- The connector never sees another agent's data, and never decides: it carries your changes and your answers.
