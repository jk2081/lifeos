---
name: lifeos-file-work
description: File work done with the owner in chat (a deck, a document, an analysis made from files he sent) into Life OS so it can be found and used later. Use whenever the owner asks to file, keep or save something into Life OS, and at the end of any task in which you produced files for him. Needs the lifeos skill.
---

# Filing work into Life OS

Life OS is not a filing cabinet. A capture is raw material; what matters is what is made from it. When the owner sends you files, asks you to make something from them, and asks you to keep it, file **five things**, not one box:

1. the **inputs**, once each, so they can be reused;
2. the **output**, as a capture you process yourself, with a summary and proposals;
3. a **wiki page** for each organisation or person the work is about;
4. a **chat log** of the conversation;
5. **nothing invented**: no instruction, date or fact the owner did not give.

Follow the `lifeos` skill for every call, rule and refusal. This file only says how to put a piece of work together.

## 0. Before you start

- Call `lifeos.api.meta.proposal_schema` once.
- Decide the **space** (Private unless the owner says otherwise) and the **area** from the context's areas (`lifeos.api.meta.space_context`). Never invent an area.
- Pick one **job id** for the work: `<organisation-or-topic>-<what>-<YYYY-MM-DD>`, lower case, for example `mehi-motors-pitch-2026-11-19`. Every record below uses it, so filing the same job twice updates instead of duplicating.

## 1. Inputs: keep each reusable input once

Inputs are what the owner gave you: his standard deck, brand guidelines, a template, a screenshot, notes.

- **Search first.** `lifeos.api.search.query` (`text` = the file's name or title) and `lifeos.api.sources.list`. If the same input is already in Life OS, do not file it again; use the existing item's name in the links below.
- **Reusable inputs** (anything not specific to this job, such as the BTW standard deck, brand guidelines, a questionnaire template) get their own inbox item:
  - `inbox.create_item` with a plain title ("BTW standard sales deck", "BTW brand guidelines", "Dealership ERPNext fit questionnaire (template)"), `source_type` Upload, `area`, `intent` **Just keep**, `source_system` `hermes`, `external_id` a stable name for the asset, for example `btw-standard-deck`, `btw-brand-guidelines`, `dealership-fit-questionnaire`. When the owner later sends a newer version, the same `external_id` updates it.
  - Attach the file with `/api/method/upload_file`, keeping or improving its name (`BTW standard sales deck.pptx`, never `img_8efa4a28f542.jpg`).
  - **Sending the same file again is fine and costs nothing.** Life OS stores each file once per space, by its content: the same bytes sent to the same item answer with the file already there, and the same bytes on another item are linked, not copied. When the owner sends a **newer version**, file the item again with the same `external_id` and attach the new file **under the same name**: it becomes the current file and the old one is kept as an earlier version ("2 versions, latest 19 Nov"), not as a second attachment.
  - Claim it and `submit_result` with `transcript_md` (the extracted text, so it is searchable) and a one-line `summary_md`. No proposals: Just keep refuses them.
- **Inputs specific to this job** (for example a client's own document) go into the output item in step 2, not on their own.

## 2. The output: one capture, processed by you

The output is what you made: the deck, the PDF, the document, the analysis.

- `inbox.create_item`:
  - `title`: what it is, for whom, and the date, for example "Mehi Motors: owner-first sales deck, 19 Nov 2026".
  - `source_type` Upload, `area`, `source_system` `hermes`, `external_id` the job id.
  - `intent` **Process**. Always, even when the owner said "just file these": that phrase is about his inputs, not about work you did for him.
  - `instruction`: the owner's own words for the job, copied, not your interpretation. Never write instructions he did not give, such as "no tasks requested".
  - `raw_text`: the brief in a few lines: who it is for, what the owner asked, what you made, which inputs you used (by title).
- Attach every output file with a clear name (`Mehi Motors - Owner-first Sales Deck.pptx`, `.pdf`, `.html`).
- Claim it and send **one** `submit_result`:
  - `transcript_md`: the text of the output (slide titles and body text, or the document's text), so it is searchable.
  - `summary_md`: five to ten lines. What the work argues or concludes, how it is structured, what is still to be checked (for example "Hi-Rise, Vahan and Disha integration to be validated"), and the inputs it used, each as a `[[Title]]` link.
  - `proposals`, each for the owner to accept or reject:
    - a **Note** that is the record of the work: title as the item's, `area`, `goal` if one in the context clearly fits, body = the summary plus the list of files and inputs. This is what the owner will open later.
    - **Tasks** only for next steps the owner stated or that the work plainly needs, each with a short `preview` and an honest `confidence`. Example: "Get Mehi Motors' questionnaire scored before the demo" (the questionnaire shows 0 of 11 answered). Set `due_date` only when he gave one.
    - an **Event** or **Important Date** only when he stated the date and time ("pitching today" is not a time).
    - nothing else. Do not propose habits, ticks or goals from a work task.

The capture then leaves the Inbox once the owner has decided the proposals, and the Outbox counts it.

## 3. Wiki: the organisation or person the work is about

- `wiki.rules(space)`, then `wiki.search(space, "<organisation>", collection="Wiki")`.
- If a page exists, add what this work taught you with `wiki.update_page` (merge, never overwrite). If not, `wiki.create_page` with:
  - `title`: the organisation's full name, for example "Mehi Motors Pvt Ltd".
  - `summary`: one line ("Honda two-wheeler dealership; BTW ERPNext prospect").
  - `content_md`: only facts the owner stated or the inputs show: what they are, the systems they use now (Hi-Rise, Google Sheets, Vahan portal, Disha portal, Tally or Busy), what BTW is proposing, and links to `[[Mehi Motors: owner-first sales deck, 19 Nov 2026]]`.
  - `sources`: the output item and the chat log. `change_note`: why.
- A person (for example the dealership's owner) gets a page only when the owner named them.

## 4. Chat log

`chats.log` with:
- `title`: the job ("Mehi Motors sales deck with Hermes").
- `assistant` Other, `date`, `area`, `goal` if any, `source_system` `hermes-telegram`, `external_id` the job id.
- `summary_md`: what the owner asked, in his words where they matter (his goal for the deck, the systems to replace or integrate, the skill he asked you to apply), what you produced, and what you could not do (for example a file he mentioned but did not attach).
- `open_items`: next steps still open, as short lines. They are not tasks until he presses Make task.

## 5. Tell the owner, briefly

One message: what you filed and where ("Inputs: 3 kept, 1 already there. Output: Mehi Motors deck, with a note and 1 task waiting for you in the Inbox. Wiki: Mehi Motors Pvt Ltd. Chat logged."), and the link to the output in Life OS (`https://life.jaikejriwal.com/life/inbox`).

## Things not to do

- Do not put inputs and outputs in one capture.
- Do not leave a capture you created in New: claim and process it in the same run.
- Do not put the description in `raw_text` and leave the summary empty.
- Do not link meetings yourself (agents cannot). Life OS links today's meeting with Mehi Motors from the calendar and the times, if it is on the calendar.
- Do not copy secrets, full account numbers or anything sensitive into the summary, the wiki or the chat log.

## Fixing work filed the old way

If a job was filed as one box (inputs and outputs together, status New), re-file it with this recipe:

1. File the reusable inputs as in step 1.
2. Call `inbox.create_item` again with the **same `external_id`** as the old item, the output-only title, `intent` Process and the brief as above. Life OS updates the old item instead of making a second one. Attach the output files; any already on it are recognised by their content and not attached twice.
3. Process it as in step 2, then do steps 3 to 5.

You cannot delete the old files on that item. Tell the owner which input files are still attached to it, so he can remove them in the app if he wants.
