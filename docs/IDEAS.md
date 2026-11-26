# Ideas

Thoughts about Life OS that are not issues yet. **Nothing here is built by the runner.** An idea becomes work only when it is written as a GitHub issue labelled `ready`. When that happens, move the idea's line to "Became issues" with the number.

Each idea keeps the owner's own words, then a short note on what it would take.

## Open

### The Brain page, cleaned up
> "Inbox" title inside Brain; Needs you and Queue › To review are the same thing twice; Captures is not a tab; footer links repeat the tabs. (25 Nov)

Brain gets one title and four tabs: Needs you · Captures (with Filed / Working on it / Failed as chips) · Activity (with the Outbox inside it) · Sources. The footer links go. List tools appear only past about ten rows. "Agent" becomes "the Brain" wherever it means the Brain.

### "Update available" where you can see it
Settings › Advanced › Updates is hard to find. The setup card (bottom left) shows "Update available · Update now" when `main` is ahead of the site.

### Hand a job to your assistant from Life OS
> "no hermes can make changes - why dont you tell hermes to do it." (26 Nov)

Life OS (or Chat) puts a request ("cancel the Twinings meet") in the queue the connector pulls. The assistant does it on its next run and reports back the result. This needs one more kind of change in `agent/connector`.

### WhatsApp
> "How can I ingest WhatsApp as a source. Official is not possible." (24 Nov)

- Life OS in the phone's share sheet (partly in #120).
- An importer for WhatsApp's "Export chat" (.txt plus media): dated messages, filed under the person, media read locally.
- Later, if forwarding gets tiresome: the assistant on a second number through Meta's Cloud API.
- Not unofficial libraries on the main number (they break WhatsApp's terms and risk a ban).

### Forms: collect information from people by link
> "think of normal use cases that involve form building, data gathering and storing and sharing as a link and collecting info" (25 Nov)

Built on Frappe's runtime DocTypes, Web Form and Report Builder.
- Describe it in a sentence, preview and test, then share by personal links or a public link or QR.
- Responses become records on the right pages, with reminders and alerts.
- First cases: the estates' daily reports, a board vote, BTW discovery questionnaires.

### Dashboards described in a sentence
> "form builder, then dashboard from the data inside lifeos - create my dashboard type of page" (25 Nov)

Pages of blocks (number cards, charts, tables), stored as Frappe Dashboard Chart and Number Card records and drawn in Life OS's style. Pinned like any page. Chat can explain them.

### Chat on a ChatGPT plan
> "i would like to add chatgpt signin as a way to use chatgpt for ask" (24 Nov)

Life OS itself can't offer ChatGPT sign-in without being an approved OpenAI partner. The assistant (Hermes) can already run on a ChatGPT plan, so Chat could fall back to the assistant when there is no AI key.

### Speak into any note box
A mic button in Life OS's own text boxes, using faster-whisper on the server (#104). Part of #120 for the chat; this would add it everywhere else.

## The owner's own steps (not code)
- Review Hermes's four Life OS skills (`lifeos`, `life-filing`, `lifeos-file-work`, `email-digest-lifeos`) against today's Life OS; drop the digest one (Life OS writes the digest now).
- Register Life OS in Azure, so Microsoft mail can be connected.
- Run Flow's server under Supervisor when #119 lands.
- Choose a product name. "Life OS" stays until there are paying users; Saarthi and Helm are taken in software.

## Became issues
- Simple mode (no goals and areas, areas suggested from use): #109 (held).
- A learning Brain, rules, plate vs waiting pile: #117, #118.
- Chat on Flow, renamed from Ask: #119. Chat everywhere: #120.
