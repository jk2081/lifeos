# Status

Build of Life OS v1. Updated at the end of every milestone.

## Milestones

| Milestone | State |
| --- | --- |
| M0 Skeleton | Done |
| M1 Spaces and permissions | In progress |
| M2 Data model | Not started |
| M3 Inbox and review | Not started |
| M4 Tasks and Today | Not started |
| M5 Journal | Not started |
| M6 Calendar | Not started |
| M7 Library and Vault | Not started |
| M8 Search and graph | Not started |
| M9 Polish | Not started |

## M0 Skeleton

- Works: Docker stack (`docker/docker-compose.yml`), bench on Frappe 16.56.0, test site `lifeos.localhost` on host port 18000, `lifeos` app installed, front-end scaffold (Vue 3, Vite, Tailwind, frappe-ui 1.2.0) served at `/life` behind login, sidebar and phone tab bar as in the mockups.
- Stubbed: every screen shows a placeholder until its milestone.
- Tests: `lifeos/tests/test_m0_skeleton.py` passes.

## How to run the local stack

```
docker compose -f docker/docker-compose.yml up -d
docker exec -d lifeos-bench bash -lc 'cd ~/frappe-bench && bench serve --port 8000'
cd frontend && npx vite build        # rebuild the front end
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench && bench --site lifeos.localhost run-tests --app lifeos'
```
