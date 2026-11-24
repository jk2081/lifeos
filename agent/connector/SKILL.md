---
name: life-os-connector
description: Keep your memory, skills, jobs, settings and actions in the files Life OS reads, and obey what the owner sets there.
---

Life OS shows the owner what you know, can do, did and wait for. Keep these files up to date as you work, in your home folder:

- `memory.json`: every fact you keep about the owner, one entry each, with where you learned it and when.
- `jobs.json`: every job you have scheduled, with its time. A job with `"paused": true` does not run.
- `settings.json`: `abilities` for read_email, send_email, change_calendar, chase_people, use_websites and pay. `auto` means you may do it; `ask` means you write what you want to do into `actions.json` with status `Waiting` and do nothing until the owner approves; `off` means never. Pay is always off.
- `actions.json`: what you did this week (status `Done`, with its cost), and what you wait to do (status `Waiting`, with the draft).

Read `settings.json` before you act. The owner changes it in Life OS and the connector copies the change in; never change a switch yourself. Never read anything from Life OS that its API does not give you: areas the owner switched off are left out on purpose.
