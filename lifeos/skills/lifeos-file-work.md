---
name: lifeos-file-work
title: File work done in chat
when_to_use: The owner asks to file, keep or save work done with him in chat (a deck, a document, an analysis made from files he sent), and at the end of any task in which you produced files for him. Needs the lifeos skill.
trigger: Served
output: Answer
model: Smart
version: 2
---

# Filing work into Life OS

Life OS is not a filing cabinet. A capture is raw material; what matters is what is made from it. When the owner sends you files, asks you to make something from them, and asks you to keep it, the work is **one job**, filed with **one call**: `lifeos.api.jobs.file_job`. Life OS makes one inbox item for it, keeps the reusable inputs once each, attaches the outputs, puts your proposals in front of the owner, and writes the wiki pages and the chat log, all linked to the item.

Follow the `lifeos` skill for every rule and refusal. This file only says how to put a job together.

## The rules

1. **One job, one item, one call.** Never file inputs and outputs as separate captures, and never put them in one box of files.
2. **Nothing invented.** No instruction, date, fact, task or person the owner did not give or the work does not plainly show.
3. **The owner's words for the instruction**, copied, not your interpretation. Never write instructions he did not give, such as "no tasks requested".
4. **No secrets.** No passwords, keys, full account, card or ID numbers in the summary, the wiki or the chat log.

## Before the call

- Call `lifeos.api.context.get` first (the `lifeos` skill says how): the core card and the index tell you who the owner is and which pages exist, so you do not guess or ask. Open only the pages you need.
- Call `lifeos.api.meta.proposal_schema` once, and `lifeos.api.meta.space_context` for the space's areas and goals.
- Decide the **space** (Private unless the owner says otherwise) and the **area** from the context. Never invent an area.
- Pick the **job id**: `<organisation-or-topic>-<what>-<YYYY-MM-DD>`, lower case, for example `mehi-motors-pitch-2026-11-19`. Keep it: filing the same job id again **updates** the job and creates nothing new.
- For each input, decide whether it is **reusable** (anything not specific to this job: the BTW standard deck, brand guidelines, a questionnaire template) and give it a stable **asset id** (`reusable_as`): `btw-standard-deck`, `btw-brand-guidelines`, `dealership-fit-questionnaire`. Use the same id every time you meet that input again. A client's own document is an input of this job only: leave `reusable_as` out.

## The call

`lifeos.api.jobs.file_job` (POST), with:

| Argument | What to send |
| --- | --- |
| `job_id` | The job id above. Required. |
| `space`, `area`, `goal` | From the context. `goal` only when one clearly fits. |
| `source_system` | Your system, for example `hermes`. |
| `title` | What it is, for whom, and the date: "Mehi Motors: owner-first sales deck, 19 Nov 2026". |
| `instruction` | The owner's own words for the job. |
| `raw_text` | The brief in a few lines: who it is for, what the owner asked, what you made, which inputs you used (by title). |
| `inputs` | `[{name, file, reusable_as, title}]`: what the owner gave you. `name` is a clear file name ("BTW standard sales deck.pptx", never `img_8efa4a28f542.jpg`); `title` a plain title for a reusable input ("BTW standard sales deck"). |
| `outputs` | `[{name, file}]`: what you made, each with a clear name ("Mehi Motors - Owner-first Sales Deck.pptx", `.pdf`, `.html`). |
| `transcript_md` | The text of the output (slide titles and body text, or the document's text), so it is searchable. |
| `summary_md` | Five to ten lines: what the work argues or concludes, how it is structured, what is still to be checked ("Hi-Rise, Vahan and Disha integration to be validated"), and the inputs it used, each as a `[[Title]]` link. |
| `proposals` | As in `submit_result` (below). They wait for the owner. |
| `wiki` | `[{title, summary, content_md, base_version}]` (below). |
| `chat` | `{title, summary_md, open_items, source_system, assistant}` (below). |

`file` is the file's bytes in base64 (a `data:` URL is fine), or the URL of a file already in Life OS in this space (`/private/files/...`). **Sending the same file again is fine and costs nothing**: Life OS stores each file once per space by its content. For a reusable input already kept, you may send `reusable_as` with no `file` at all: the kept one is linked. When the owner sends a **newer version** of an input or you remake an output, send it under the **same name**: it becomes the current file and the old one is kept as an earlier version.

### Proposals

Each is `{kind, preview, payload, confidence, reason, alt_area}`, for the owner to accept or reject. Send a `reason` on every proposal: one short line on why, or what made you unsure (the owner reads it on Needs you). Send `alt_area` only when two areas are both likely: an area that is on, in this space, and different from the payload's `area`:

- a **Note** that is the record of the work: title as the job's, `area`, `goal` if one fits, body = the summary plus the list of files and inputs. This is what the owner will open later.
- **Tasks** only for next steps the owner stated or that the work plainly needs, each with a short `preview` and an honest `confidence`. Example: "Get Mehi Motors' questionnaire scored before the demo" (the questionnaire shows 0 of 11 answered). Set `due_date` only when he gave one.
- an **Event** or **Important Date** only when he stated the date and time ("pitching today" is not a time).
- nothing else: no habits, ticks, goals or readings from a work task.

Filing the job again keeps the proposals it sends that are already there (by kind and payload), adds new ones, and removes the pending ones it no longer sends. Accepted and rejected proposals are never touched. You cannot accept or reject anything.

### Wiki

For the organisation or person the work is about. Call `wiki.rules(space)` and `wiki.search(space, "<organisation>", collection="Wiki")` first.

- `title`: the organisation's full name ("Mehi Motors Pvt Ltd"); a person only when the owner named them.
- `summary`: one line ("Honda two-wheeler dealership; BTW ERPNext prospect").
- `content_md`: only facts the owner stated or the inputs show: what they are, the systems they use now (Hi-Rise, Google Sheets, Vahan portal, Disha portal, Tally or Busy), what BTW is proposing, and a link to the job: `[[Mehi Motors: owner-first sales deck, 19 Nov 2026]]`.
- **Merging into a page that exists.** Read it with `wiki.get_page` and send your merged text with its `version` as `base_version`: your text then replaces the page's. Without `base_version`, your text is added below the page's own (unless the page already holds it); on a page this job wrote last, it replaces it. If the page changed after you read it, the whole call is refused (`wiki[0]: base_version ...`): read it again and merge.

Every page cites the job's item and its chat log.

### Chat log

- `title`: the job ("Mehi Motors sales deck with Hermes"); `assistant` Other; `source_system` where the chat happened (`hermes-telegram`).
- `summary_md`: what the owner asked, in his words where they matter (his goal for the deck, the systems to replace or integrate, the skill he asked you to apply), what you produced, and what you could not do (for example a file he mentioned but did not attach).
- `open_items`: next steps still open, as short lines. They are not tasks until he presses Make task.

## The answer, and telling the owner

If any part is invalid, **nothing is saved** and the error names the field (`outputs[1].file: ...`, `proposals[0]: ...`). Fix it and send the whole call again.

Otherwise the answer has `item`, `url`, `created` (or `changed_fields` when it updated the job), `outputs` and `inputs` (with `attached` and `asset_created`, so you can tell what was new), `proposals.waiting`, `wiki` and `chat`. Send the owner one short message: what you filed and where ("Mehi Motors deck filed: 2 outputs, 3 inputs (1 already kept), a note and 1 task waiting for you. Wiki: Mehi Motors Pvt Ltd. Chat logged."), with the `url`.

## Things not to do

- Do not file the inputs, the output, the wiki and the chat with separate calls.
- Do not set `intent`, claim the item or call `submit_result` for a job: the one call does it.
- Do not link meetings yourself (agents cannot). Life OS links today's meeting with the client from the calendar and the times, if it is on the calendar.

## Fixing work filed the old way

If a job was filed as one box (inputs and outputs together, status New), file it again with `file_job` and the **same job id** as the old item's `external_id`. Life OS takes over that item instead of making a second one: it becomes the job's item, with the outputs, inputs, summary and proposals of this call. Files already on it are recognised by their content and not attached twice.

You cannot remove files from that item. Tell the owner which input files are still attached to it as outputs, so he can remove them in the app if he wants.
