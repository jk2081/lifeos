# UX fixes, set 4: Sources, the Wiki, a real editor, and streams

Life OS will hold thousands of captures (voice notes, PDFs, photos, articles, email digests, chat logs) and a smaller layer of pages written about them. This set gives the captures a home (Sources), turns part of Notes into a wiki an agent maintains (after Karpathy's "LLM wiki" pattern), replaces the split-pane Markdown editor with one that is formatted as you type, and prepares the app to receive continuous streams (email digests, chat logs) without duplicates.

**This set needs set 3.** If `UX_FIXES_3_DONE` does not exist, write "Set 4 needs set 3 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md`, `STATUS.md`, `DECISIONS.md` and `frontend/COMPONENTS.md` first. Follow the three-layer component rule and the tab rules from sets 2 and 3. Read a component's source before using it.

## The model in one paragraph

A **source** is anything captured, kept unchanged: today's `Life Inbox Item` (files, voice, photos, pasted text, web links, emails) and `Life Chat Log`. The **Inbox** is a queue: the sources not yet finished. **Sources** is the library of every source, finished or not. **Notes** are pages: **My notes**, which only people change (agents propose), and the **Wiki**, which an agent writes and edits directly, every change logged with one-click undo. Wiki pages cite the sources they came from. Do not merge or rename DocTypes; this is a change of screens, fields and rules.

## 0. Clean up first

- **Test debris.** The acceptance script creates records on the test site and never removes them ("Sanitise …", "UX inbox …", "S3 agent item …" and others; find every title pattern `tools/acceptance.mjs` and `tools/*.mjs` use). Delete all such records on `lifeos.localhost` with their proposals, links, index rows, files and child rows. Keep the seed data from spec section 11 and anything not created by a test.
- **Stop it recurring.** Preferred: run acceptance against a second site (`acceptance.localhost`) on the same bench, re-seeded before each run, so `lifeos.localhost` stays clean for the owner. If that is not workable with the current Docker and browser setup, every acceptance check must delete what it creates in a `finally` block, and the script ends by asserting that no record with a test title pattern remains. Record which in `DECISIONS.md`.
- **Archived areas leak into list filters.** The Area quick filter on Tasks (and likely every list built on the `@framework/ui` filter controls) lists archived areas, such as the "UX3 area A/B …" rows set 3's own test leaves archived. Set 3 checked only `area.tree` and `meta.space_context`, not the filter controls. Fix it at the source: every Link-type filter, quick filter and picker for `Life Area`, `Life Tag`, `Life Habit`, `Life Dimension` and `Life Project` goes through one helper in `frontend/src/framework/` that adds the current space and `is_archived = 0` (projects: not Done, Dropped or archived, unless the list's state tab says otherwise). The Archive screen is the one exception: its area filter includes archived areas, marked "(archived)". Add an acceptance check that opens the Area filter on Tasks, Projects, Sources and the Wiki and finds no archived area and no area from another space.
- **Test areas.** The set 3 test also leaves its "UX3 area" rows behind, archived. Remove them with the rest of the debris, and make that test delete its areas at the end.
- **Stray folders.** `lifeos/life/doctype/` contains two folders with spaces in their names (`life_tag LifeTag tag_name tag`, `life_dimension LifeDimension dimension_name dimension`), left by a broken command. Confirm nothing imports them and delete them.

## 1. Data changes

All with patches that leave existing rows valid. Add unit tests for each rule.

**`Life Inbox Item`**
- `intent`, Select: Process (default), Add to wiki, Just keep.
- `media_kind`, Select, set on save from the attached file's type or the source type: Voice, Document, Photo, Article, Email, Email Digest, Text. Patch existing rows.
- Add `Email Digest` to `source_type`.
- `source_system` (Data, for example `gmail`, `claude`, `chatgpt`, `upload`) and `external_id` (Data). Unique together with `space` when `external_id` is set.
- `thumbnail` (Attach Image, private): for photos, a copy about 480 px wide made on upload with Pillow. For PDFs, a first-page image if `pdftoppm` is available in the container; otherwise none (note it in `DECISIONS.md`).

**`Life Chat Log`**
- `source_system`, `external_id` (unique with `space`, as above), `transcript_md` (Long Text), `updated_on` (Datetime, the chat's last activity).
- Add `Codex` and `Claude Code` to `assistant`.

**`Life Note`**
- `collection`, Select: My notes (default), Wiki. Patch: every existing note is My notes.
- `summary`, Small Text: one line. Required for Wiki pages, optional for My notes.
- `sources`, Table: new child `Life Note Source` (`source_doctype`, `source_name`), allowing `Life Inbox Item` and `Life Chat Log`.
- `is_rules`, Check: marks the one Wiki rules page per space.

**`Life Wiki Change`** (new): `space`, `note`, `change_type` (Created, Edited, Reverted, Moved to My notes, Moved to Wiki), `by` (User), `on` (Datetime), `change_note` (Small Text, the agent's one-line reason), `source_doctype`/`source_name` (the source that prompted it, optional), `before_md` (Long Text), `after_md` (Long Text), `reverted` (Check). Readable by members of the space; written only by the app.

**`Life Connection`** (new): `space`, `system` (Data, for example `gmail`, `claude`, `chatgpt`, `google-calendar`), `label`, `default_area`, `default_project`, `default_intent`, `active`, `last_received_on` (set by the app when something arrives from that system). One row per space and system.

**`Life Task`**: `source_url` already exists. Use it for "Open in Gmail" and similar links; show it as a button in the task pane when set.

**Search.** `Life Index.search_text` for inbox items and chat logs must include the transcript, extracted text and summary, capped at a size you choose and record (for example the first 60,000 characters). Wiki and My notes pages index their full Markdown up to the same cap.

## 2. Inbox and Sources

### Inbox: the queue

- Tabs: **To review**, **Waiting for the agent**, **Failed**. Remove the Done tab; in its place a quiet link "Finished items are in Sources".
- The drop box gains the intent choice as `TabButtons` beside the instruction field: Process, Add to wiki, Just keep. Process is the default; the last choice is remembered per user.
- **Just keep**: the agent still extracts text (transcript, OCR, PDF text) so it is searchable, but proposes nothing. When the text is in, the item is Done without review.
- **Add to wiki**: the agent extracts text and updates wiki pages directly (section 4). Any other proposals it makes (tasks, events) still go to review. When nothing is pending, the item is Done.
- **Process**: as today.
- `claim_next` returns `intent` and the space's `Life Connection` defaults for the item's `source_system`. Agents must respect the intent; `submit_result` refuses proposals on a Just keep item.

### Sources: the library

New screen at `/sources`, built on `ListView`, reading from `Life Index` over inbox items and chat logs.

- **Tabs:** All, Chats, Voice, Documents, Photos, Articles, Email (Email and Email Digest), Text. Counts as in set 3.
- **Default view:** list, newest first. Columns: title, kind icon, received, area, status (In Inbox, Done, Failed), what was made from it (count). **Photos** tab defaults to a grid of thumbnails; the grid is also a view choice on All.
- **Filters:** area, project, date range, status, intent, system, assistant (for chats).
- **Pane tabs:** Original (audio player, PDF viewer, image, email or text, link out), Text (transcript or extracted text, editable by people as today), Summary, Made from this (records created from it, and wiki pages citing it), Details. A chat log's pane keeps its open items with Make task and Close, as the Chats screen does today.
- **Vault rule:** a source whose accepted proposal created a Vault document follows Vault access: hidden from agents unless the space's switch allows it, and shown as locked to people who cannot see the Vault.
- `/chats` keeps working and redirects to `/sources?tab=chats` with any filters carried over. The chat report view (grouped by day) moves to a view choice on the Chats tab.

## 3. The editor

Replace the split-pane editor (raw Markdown on the left, preview on the right, Edit and Done buttons) everywhere Markdown is edited: notes and wiki pages, journal pages, task and project notes, transcripts.

- **One pane, formatted as you type,** built on the existing CodeMirror 6 setup with decorations (the approach Obsidian uses). Headings render at size, bold and italic render, lists and checklists render with clickable boxes, links render as links (⌘-click or click when not editing to follow), `[[links]]` render as chips, images render inline, horizontal rules and block quotes render. The Markdown markers on a line show only while the cursor is on that line. Tables render as a table when the cursor is outside them and as text inside them.
- **No modes.** Remove Edit, Done and Hide preview. Click and type; save as today with the quiet "Saved" state. "Show Markdown" in the ⋯ menu switches to the plain text view.
- **One typeface** for writing and reading: the app's reading typeface and size from set 2. A readable column, at most about 720 px wide, centred in the pane.
- **Toolbar:** keep it small and above the text (bold, italic, heading, lists, checklist, link, `[[`, image). On a phone it sits above the keyboard.
- **Shortcuts:** ⌘B, ⌘I, ⌘K (link), ⌘⇧7 and ⌘⇧8 (lists), Tab and Shift-Tab to indent list items.
- **`/` menu** at the start of a line: heading 1 to 3, bulleted list, numbered list, checklist, table, quote, divider, link to a record.
- **Images:** paste or drop an image to upload it as a private file attached to the note and insert it.
- **Filing as one line** under the title: "Business That Works · no project · in <parent> · edited 16 Nov". Clicking it opens a small popover with the area, project, parent note and also-in pickers. Remove the row of chips.
- **Conflicts.** Every save sends the version it started from. If the page changed since (an agent edit, another device), do not overwrite: show "This page changed while you were editing" with View changes, Keep mine and Reload.
- **Prove it first.** Build the editor on a development-only page (`/life/dev/editor`, owner only, not in the sidebar) with a sample note that uses every element above. Screenshot it at 1440 px and 390 px, light and dark, and fix what looks wrong before replacing the editor anywhere else.
- Keep the existing Markdown sanitising on render. Nothing typed in a note may run script.

## 4. Notes and the Wiki

### Two screens

- **Notes** (`/library`, label Notes) shows My notes only. Default view **List** (title, area, updated), newest first, with Tree and Graph as view choices. The tree is grouped by area and collapses; it never lists more than 50 children under one heading without a "Show all" row.
- **Wiki** (`/wiki`, new) shows Wiki pages. Tabs: **Pages** (list with title, summary, area, sources count, updated; Graph as a view choice), **Changes**, **Health**, **Rules**.
- A page opens in the pane and full page as notes do. The pane for a wiki page has tabs Page, Sources, Links, History.
- Search, links, backlinks, the graph and area pages cover both collections. Area pages get a Wiki tab beside Notes.

### Who can change what

- **My notes:** people only. Agents can propose a note (as now) but cannot create or edit a My notes page directly.
- **Wiki:** agents with edit access to the space create and edit pages directly, through the methods below. People edit them like any note. Every create, edit and revert, by anyone, writes a `Life Wiki Change`.
- **Move between collections:** on any page, "Keep in My notes" (Wiki to My notes) and "Hand to the wiki" (My notes to Wiki), for people only. A page moved to My notes can no longer be changed by agents.
- **Rules page:** one per space, `is_rules` set, created on first visit to the Wiki with a starter text (what the wiki is for, page naming, one page per person, organisation, concept and source; always cite sources; summaries in one line; prefer editing an existing page over creating a near-duplicate; never copy secrets or full account numbers). People edit it. Agents can read it and cannot change it.

### Changes and undo

- **Changes tab:** every `Life Wiki Change`, newest first, filterable by page, by person or agent, by source and by date. Each row shows the page, who, when, the change note, and the source that prompted it.
- **Opening a change** shows a readable line diff of `before_md` and `after_md` (use a small diff library such as `diff`; record which in `COMPONENTS.md`).
- **Undo:** restores `before_md` if the page has not changed since that change, writing a Reverted change. If it has changed since, show the diff against the current page and let the person choose: revert anyway, or open the page.
- A page's History tab shows its own changes the same way.

### Health

Computed by the app, refreshed nightly and on demand:
- Orphans: wiki pages no other page links to (rules page excepted).
- Broken links: `[[Title]]` that resolve to nothing. Clicking one offers "Create this page".
- Pages without sources.
- Near-duplicate titles (same title ignoring case and punctuation).
Each list links to the pages. The agent's own judgement (contradictions, stale claims) comes later as reports it files as wiki pages tagged `health-report`; show those at the top of the Health tab when present.

### Links

Keep the existing `[[Title]]` and `[[Title#name]]` syntax and resolution. Agents write plain `[[Title]]`; resolve within the page's space, preferring a Wiki page, then a My notes page, then other records. Ambiguous links render with a warning and appear under Health.

### Agent methods (new module `lifeos.api.wiki`)

All take `space` where relevant, enforce space membership, edit access and the Vault rule, and are listed in `agent/SKILL.md` with examples.

| Method | Does |
| --- | --- |
| `rules(space)` | The rules page text |
| `index(space, area=None, start, page_length)` | Wiki pages: name, title, summary, area, sources count, updated. Paginated |
| `get_page(name)` | Title, Markdown, summary, area, sources, links, and a `version` token |
| `search(space, query, collection=None)` | Full-text search over pages (and sources when asked), with snippets |
| `create_page(space, title, content_md, summary, area=None, project=None, parent_note=None, sources=[], change_note, source=None)` | Creates a Wiki page and a Created change. Refuses a title that already exists in the space's Wiki |
| `update_page(name, content_md, base_version, summary=None, sources_add=[], change_note, source=None)` | Edits a Wiki page if `base_version` is current; otherwise returns a conflict with the current version, never overwrites. Refuses My notes pages and the rules page |
| `cite(name, sources)` | Adds sources to a page without changing its text |

Limits: page Markdown up to 200,000 characters; a single call cannot change more than one page. Record any other limit you add.

Update `agent/fake_agent.py` so that for an Add to wiki item it creates one page and edits another through these methods, and use it in tests.

## 5. Streams: original IDs, connections, digests, imports

### No duplicates

`inbox.create_item` and `chats.log` accept `source_system` and `external_id`. When a record with the same space, system and ID exists, update it instead of creating another:
- An inbox item: update text fields and files; if it was Done and the new content differs, set it back to New so the agent processes the change, and record that in its history.
- A chat log: update title, `updated_on`, summary and transcript; merge open items by text (add new ones, keep closed ones closed).
Both return whether they created or updated. Update `Life Connection.last_received_on` for the space and system.

### Connections (Settings > This space > Connections)

One row per system: label, default area and project, default intent, active, and "Last received" (for example "Email digest, today 07:02"). Show a warning on the row if nothing has arrived for longer than a threshold you set per system (2 days for email and chats). Agents read the defaults through `claim_next` and a `connections.defaults(space, system)` method. No credentials are stored or shown here; the agents hold their own access.

### Email digests

- An `Email Digest` source shows its Markdown with sections (Needs your attention, Waiting on others, Dates and deadlines, FYI from people, Company information, Left out) rendered as headed lists, each item's Gmail link as an "Open in Gmail" button.
- A proposed task from a digest carries the thread link in `source_url`; the task pane shows "Open in Gmail".
- Digest sources default to the Sources Email tab and to the intent set in the connection (Process by default, so proposed tasks reach review).

### Chat export import (Settings > This space > Connections > Import)

- Upload a Claude data export or a ChatGPT data export (a `.zip`, up to 1 GB). Store it as a private file and process it in a background job with progress shown on the screen; the owner can leave the page.
- Read `conversations.json` from either. Claude: each conversation's UUID, name, created and updated times and messages. ChatGPT: each conversation's ID, title, create and update times and the message tree (walk the current branch). Tolerate unknown fields; skip and count conversations that cannot be read.
- For each conversation, create or update a `Life Chat Log` by `source_system` and `external_id`: title, `date` (created), `updated_on`, `url` (`https://claude.ai/chat/<uuid>` or `https://chatgpt.com/c/<id>`), `assistant`, and `transcript_md` (speaker, time, text; attachments as names only). Leave `summary_md` empty; such logs show "Not summarised yet" and are listed for agents by a `chats.needs_summary(space)` method so an agent can fill them later.
- Area and project come from the connection's defaults; the owner can re-file in bulk from the Sources list (multi-select, set area).
- Test with small synthetic exports built from the documented formats, kept in `lifeos/tests/fixtures/`. If the real format proves different when the owner runs an import, the job must fail cleanly with a count of what it could not read, not a partial mess.
- The export does not say which Claude project a chat belonged to. Do not guess.

## 6. Sidebar

The Records group becomes **Sources, Notes, Wiki, Vault, Timeline**. Chats leaves the sidebar (it is the Chats tab of Sources). Everything else in the sidebar is unchanged.

## 7. Scale

Extend the load test from milestone 9: add 20,000 sources with about 5,000 characters of text each and 2,000 wiki pages. With that data, at 1440 px: Sources first page, a Sources tab switch, a full-text search, the Wiki Pages list, and the Changes list each answer in under 500 ms on the server. Record the timings in `STATUS.md`. Thumbnails, not full images, load in the Photos grid.

## What must not change

- Existing records, links, proposals and history. Nothing is deleted except the test debris and stray folders in section 0.
- Space rules, the Vault switch, desk access and the agent-role rule from set 3.
- The Inbox review flow for proposals, apart from the intent choice.
- The shared rules from sets 1 to 3: list and pane pattern, remembered views, tabs in the URL, three-layer components.

## Checks

Add to `tools/acceptance.mjs`, at 1440 px and 390 px, each cleaning up after itself:

- No test debris remains on `lifeos.localhost` after a full acceptance run.
- **Intent:** drop a text item as Just keep; once the fake agent has run it is in Sources, not in the Inbox, has text, and has no proposals. Process works as before. Add to wiki creates and edits wiki pages and leaves no wiki proposals for review.
- **Sources:** each tab's count matches its rows; the Photos grid shows thumbnails; a source's Made from this tab lists the task and the wiki page made from it; `/chats` redirects to the Chats tab.
- **Editor:** type `## Title`, `**bold**`, a checklist and a `[[` link on the dev page and in a real note; each renders formatted when the cursor leaves the line; ⌘B works; the `/` menu inserts a table; a pasted image uploads and shows; "Show Markdown" shows the raw text; no Edit or Done button exists. At 390 px the toolbar is usable.
- **Conflict:** open a wiki page, have the fake agent edit it through `update_page`, then type and save: the conflict message appears and nothing is lost.
- **Wiki rules:** the fake agent cannot edit a My notes page or the rules page; an `update_page` with a stale `base_version` returns a conflict. Undo restores the previous text and writes a Reverted change. Keep in My notes stops further agent edits.
- **Health:** a page with a broken `[[link]]` and an orphan page appear under Health.
- **Streams:** calling `chats.log` twice with the same `external_id` leaves one log, updated. Importing the Claude and ChatGPT fixtures creates the expected logs; importing again creates none and updates none that did not change.
- **Digest:** an Email Digest source renders its sections and Open in Gmail buttons; a proposed reply task shows Open in Gmail after acceptance.
- **Sidebar:** Records shows Sources, Notes, Wiki, Vault, Timeline.
- **Access:** the family test user sees no Private sources, pages or changes; the agent cannot see a source behind a Vault document while the switch is off.

Unit tests for every data rule above. Screenshot every new or changed screen at both widths in light and dark, look at each, and fix what is broken. Update `frontend/COMPONENTS.md` (editor, diff view, Sources grid) and `agent/SKILL.md` (intent, wiki methods, external IDs, connections, needs_summary).

## Working rules

- Order: 0 cleanup; 1 data changes; 3 editor on the dev page, then everywhere; 2 Inbox and Sources; 4 Notes and Wiki; 5 streams; 6 sidebar; 7 scale; then checks.
- Run the acceptance script after each step and commit once per step.
- Record deviations in `DECISIONS.md`. Add a "UX fixes, set 4" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_4_DONE` and commit.
