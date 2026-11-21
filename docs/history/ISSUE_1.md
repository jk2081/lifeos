# Issue 1: people and agents in one place

Do everything in GitHub issue #1, "Settings: put people and agents in one place". Its text is copied below so this file stands on its own. Where the two differ, this file wins.

**This fix needs set 8.** If `UX_FIXES_8_DONE` does not exist, write "Issue 1 needs set 8 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md` (including "Frappe conventions"), `STATUS.md`, `DECISIONS.md` and `frontend/COMPONENTS.md` first. Follow the Frappe skills in `.claude/skills/` and the components rule. Every screen must work at 390 px and 1440 px, light and dark.

## The problem

Who can see and do what is set in four places in Settings:

| What | Where it is today |
| --- | --- |
| Spaces | People and agents → Spaces |
| People in a space | People and agents → Members (agents are filtered out) |
| Agents in a space, and their access | Assistant → Assistants |
| Whether agents may open sensitive items | Assistant → Sensitive items |
| Whether Ask works in a space | Assistant → Ask and AI |

On 19 November 2026 the owner added `claude-jai` and `hermes-jai` to Private with **Add member**. Both were saved, but neither appeared in the list, because `_member_rows` in `lifeos/api/settings.py` drops users with the Life Agent role. The footer says "Agents are under Agents", and there is no item called Agents in that group.

## What we want

One section, **People and agents**, that answers "who is in this space and what can they do". Everyone a space has, human or agent, appears in one list, marked by kind. Settings about the assistant itself (AI key, cost, connections, note rules) stay under Assistant.

## Changes

### Settings menu (`frontend/src/pages/Settings.vue`)

- **People and agents** gets three items: **Spaces**, **Members**, **Agents**.
  - **Members:** everyone in the selected space, people and agents together. Each row: avatar, name, email, a kind badge (Owner, Person, Agent), access (Can view, Can edit), remove. Filters All, People, Agents, with counts.
  - **Agents:** one card per agent across all spaces (what Assistants shows today): spaces and access, last filed, sensitive-item access, and a link to its Frappe user for keys. Empty state says how to make one.
  - **Spaces:** as now, plus per space the owner, member and agent counts, **Ask in this space**, and **Agents may open sensitive items**, moved here from Ask and AI and from Sensitive items.
- **Assistant** loses **Assistants**. It keeps Connections, Ask and AI (key, models, cost and prices only), Sensitive items (the people side, with a line pointing to Spaces for agents) and Note rules.
- `?tab=agents` and any other old link redirect to the new places.

### Add member

- Searches all users (`find_users`) and shows each result's kind.
- Adding an agent adds it with the access chosen; the row appears at once with its Agent badge.
- Default access: Can edit for people, Can view for agents, with the note "Agents need Can edit to file captures and proposals".
- A user with no Life OS role: say so and offer the role that fits (Life User for a person, Life Agent for an agent), applied only when the owner confirms. Never give an agent Life User or Life Admin.

### Server (`lifeos/api/settings.py`)

- `get` returns one `members` list per space with `is_agent` on each row; build `agents` for the Agents view from the same query.
- One method for space access: the Agents view uses `set_member`; remove any agent-only setter that duplicates it. `set_agent_vault` stays and is called from Spaces.
- Keep the rules: only Life Admin adds or removes members; the space owner cannot be removed; agents can never be owners or admins.
- Every changed or new whitelisted method keeps `methods=[...]` and type hints, per `frappe-app-dev`.

### Elsewhere

- Help text: remove "Agents are under Agents"; point Sensitive items, Ask and AI and the Agents empty state to the new places.
- `agent/SKILL.md` and `README.md`: agents are added in Settings → People and agents → Members, with Add member.
- `frontend/COMPONENTS.md`: one member row component for people and agents.

### Not in this fix

- Creating agents (Hermes profiles) from Life OS: set 12.
- Life Person records (contacts without a login): leave as they are.

## Tests: how much to run when

- **While working:** the unit tests for `lifeos/api/settings.py` and permissions, the acceptance checks for Settings, and `./tools/scan.sh` on the changed files. Do not run the full suites after every edit.
- **Once, at the end:** the full unit suite, the full `tools/acceptance.mjs` at 1440 px and 390 px, and the full scan. All must pass.

New tests:

- Unit: `get` returns agents in `members` with `is_agent`; only Life Admin can change members; the owner cannot be removed; this screen cannot give an agent Life User or Life Admin.
- Acceptance: add an agent with Add member and see it in Members with its badge and in Agents; change its access in one view and see the other match; switch Ask and sensitive-item access from Spaces; `?tab=agents` lands on People and agents → Agents; nothing under Assistant lists members or agents.

## Working rules

- Review the diff against `frappe-code-review` before finishing.
- Record anything that differs from this file in `DECISIONS.md`; add an "Issue 1: people and agents" line to `STATUS.md`.
- Commit with a message that ends "Closes #1".
- When finished, create an empty file named `ISSUE_1_DONE` and commit.
