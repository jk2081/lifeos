# Deep audit (pre-step 6, step 3)

Frappe's `deep-app-audit` skill (github.com/frappe/skills, fetched by `scripts/get-frappe-skills.sh`) was applied to `lifeos` on 17 November 2026.

## How it was run

The skill's own script (`scripts/run_audit.py`) could not run unattended here, for two reasons:

- It starts each task as a `claude -p` process on the host, with a tool allowlist of `bench --site …`, file reads under the bench, `curl` and `jq`. The bench and the Frappe source are inside the `lifeos-bench` Docker container, so those agents could neither run `bench` nor read the framework.
- A full run is about 160 scan agents plus one verifier for each candidate, over several hours.

So, as the brief allows, its checklists were worked through by hand, in four parallel passes. Each pass read the track's `_conventions.md` (and `security/_framework-guards.md`) and applied every checklist in its scope to the app. It then re-read each candidate from entry point to sink, trying to refute it. Where a proof helped, it ran Python on the bench as the owner, the family member or the agent, rolled back with no commit.

| Pass | Checklists applied | Result |
| --- | --- | --- |
| [security-A.md](audit/security-A.md) | S-A01 to S-A14 (authorization) | 3 confirmed |
| [security-B-E.md](audit/security-B-E.md) | S-B01 to S-B10, S-C01 to S-C05, S-D01 to S-D08, S-E01 to S-E04 (injection, XSS and CSRF, identity, files) | 1 confirmed |
| [security-F-L-P.md](audit/security-F-L-P.md) | S-F01 to S-L02, posture checks S-P01 to S-P05 | 3 confirmed |
| [quality.md](audit/quality.md) | Q-B01 to Q-B44 (correctness), Q-K02 (framework surface) | 4 confirmed |

**Not applied:** the `quality/A-customization` rules and Q-K01. They concern overriding ERPNext and core DocTypes; Life OS has its own DocTypes and overrides nothing. **Not applicable inside the scopes:** money (S-H03) and email (S-J01 to S-J03); each pass's table gives the reason for every check.

## Findings and what was done

The same `reset.undo` defect was found by two passes (S-A F2, rated Moderate, and S-B02, rated High). It counts once, at High.

| Id | Severity | Finding | Done |
| --- | --- | --- | --- |
| S-B02 / S-A F2 | High | `reset.undo` (`unaccept`) set a proposal and an inbox item named in the browser's undo log, with no permission check. A dict as the name matched every row. | **Fixed.** Only the proposal's name is taken from the log. It must be a string, and the proposal is loaded with a write check. The item and the record made are read from the proposal, each checked for the user. The index follows the item. Test: `test_undo_takes_only_a_proposal_this_user_may_change`. |
| S-A F1 | High | `inbox.list` showed an agent the sources that Vault documents were made from, transcripts included, in a space whose Vault switch is off. | **Fixed.** Those items are left out of every query of the method (rows, totals, tabs, summary). Test: `test_an_agent_never_lists_the_source_of_a_closed_vault`. |
| Q-B26 | High | A record pointed at by bookkeeping rows could never be deleted: the record a proposal made, insight evidence, an Ask scope, an idea's source, the source of a wiki change. This covered every task accepted from review. | **Fixed.** Those five DocTypes are in `ignore_links_on_delete`. A wiki page's cited source still blocks a delete, as set 5 decided. Test: `test_a_task_made_from_a_proposal_can_be_deleted`. |
| S-I01 / S-H05 | Moderate | `trash.list` showed agents deleted Vault documents, and deleted sources of them, while the switch is off. | **Fixed** (same kind as S-A F1, and small). Test: `test_an_agent_never_sees_a_deleted_vault_document_in_the_trash`. |
| Q-B28 | Moderate | Two status writes skipped the index: Reset's undo of accepted notes, and `release_stale_claims`. | **Half fixed:** the undo now updates the index. `release_stale_claims` puts an item back to New; the index has no New/Processing filter that a person uses, so it is left. |
| Q-B05 | Moderate | `views.save` checks then inserts, with no unique key on (user, screen, space). Two saves at the same moment can make two rows, and the older one would then win. | Recorded. Two saves from one person at the same instant are unlikely, and a unique index is a schema change. Proposed for set 6. |
| S-A F3 | Low | Agents can read Life Proposal and Life Link rows tied to a closed Vault over REST and MCP (a proposal's payload holds a title and last four digits). | Recorded. The agent wrote those proposals itself. Proposed for set 6 with the query condition. |
| S-K01 (a) | Low | `tasks.quick_add` date-word parsing is quadratic on a long run of commas (8,000 commas: 11 s). | Recorded; needs a logged-in person. Cap the text and collapse `[\s,]` runs. |
| S-K01 (b) | Low | The chat export import checks the zip's compressed size, not how large `conversations.json` unpacks. | Recorded; needs a person with Write access to upload a zip bomb. Check `ZipInfo.file_size` first. |
| Q-B40 | Low | `ai/client.api_key` swallows a decryption error without a log. Ask then says "not set up" while Settings shows a key. | Recorded. |

Informational, from the posture checks: there are no CI files in the repo; the app sets no security headers (Frappe's production nginx sets some); the Docker images in `docker/` use floating tags (local stack only). The known Python advisories are in packages Frappe pulls in and Life OS does not use. The one JS advisory is in a build-time CSS tool.

## Re-running

```
scripts/get-frappe-skills.sh            # fetch the skills, pinned
```

Then either run the skill's script from a machine where the bench runs natively (`/deep-app-audit lifeos`), or work through `security/` and `quality/B-correctness` as above. The audit's output is agent output: a person should confirm each finding before acting on it.
