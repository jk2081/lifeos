# Ideas

Thoughts about Life OS that are not issues yet. **Nothing here is built by the runner.** An idea becomes work only when it is written as a GitHub issue labelled `ready`. When that happens, move the idea's line to "Became issues" with the number.

Each idea keeps the owner's own words, then a short note on what it would take.

## Open

### Deploying to many customers: one container stack per customer
> "all of this will have to be done when this is mass deployed?" … "i imagine some kind of a saas frontend deploys a docker container on a vps as a site with all of this setup" … "each site is isolated in its own container" (26 Nov)

Decided: **each customer's site is isolated in its own container stack**, with its own web, workers, scheduler, socket.io, Flow server, MariaDB and Redis. Several stacks can share one VPS behind one proxy for domains and HTTPS. A big customer moves to a VPS of their own by moving their stack.

1. **The image.** CI builds Life OS with Frappe 16.61 (Flow included) from each merge to main, starting from Frappe's official `frappe_docker`. It comes with a compose file for one stack and a health check that prints one line per check. Each process is its own container, so there is no sudo and no Supervisor. An update pulls the new image and migrates. A rollback means the previous image plus a restore. Nothing is checked out or built on a customer's server.
2. **The control plane** (the SaaS front end): sign-up and payment, creating the customer's stack, domain and HTTPS, off-server backups (#34), rolling out updates, and every customer's version and health at a glance. **Check Frappe's first:** Frappe Cloud's control plane (Press) is open source, and BTW Central already runs Frappe Cloud site work. Verify whether Frappe Cloud runs the Flow server, and where Hermes would live.
3. **The customer's own steps,** in onboarding: connect Google, an AI key (now Flow's provider), and optionally Hermes.

Order: the updater fix (below), the image, the control plane decision, the control plane.

### The updater: check before changing, don't roll back a good migrate
> The live update failed twice on 26 Nov: `restart: failed … 'sudo supervisorctl status' returned non-zero exit status 1`, then `restore the backup: failed. bench --site exited 1:` with no reason. The site was left on old code with a migrated database.

What was found:
- The updater runs from cron with no terminal, and `frappe` had no password-free sudo for `supervisorctl`. The owner fixed it by hand with a sudoers line. Frappe's `bench setup sudoers frappe` does the same.
- `bench restore` needs the MariaDB root password, which cron can't type. So the rollback's restore could never have worked on this server.

To build:
- **Check before changing anything.** Before backup, `verify` also checks that a restart and a restore can run without a person. If not, it refuses with the one-line fix, and Settings › Updates shows a "Ready to update" list.
- **Only the restart failed:** no rollback (new code and the migrated database belong together). The status is "Needs restart", with a Restart now button.
- **A restore that works without root:** load the dump with the site's own database user (`bench --site X mariadb`).
- **Every failed step** logs its command, exit code and the last lines of stdout and stderr. Never "exited 1:" with nothing after it.
- **The Updates page shows saved values, not the truth** (26 Nov): "Installed" said 73b05f9 while the server's git was at 324cbed, and "Available" kept saying 324cbed after main had moved on. So Update now ran 324cbed → 324cbed. Read Installed from the app's own `git rev-parse HEAD`. Fetch before showing Available (or show when it was last checked). Refuse an update to the commit already installed.

The full draft issue text was written in chat on 26 Nov. Much of this goes away with the image (above), but the bench install needs it until then.

### Life in four layers, and the ladder
> "life works in two slices time and area of work/focus, is there anything else?" … "So simplest is time & people, then area (goals), then systems, then energy?" … "I think 1 & 2 are easy to understand. park this discussion in ideas but the ladder should be 1 & 2 for now." (26 Nov)

Users grow into four layers, each asking more of them than the last, and none offered before the one below pays off:

1. **Time and people.** Free: it comes from mail, calendar and contacts. Needs you, waiting on others, people's pages, delegation, Chat and WhatsApp.
2. **Areas and goals.** Takes intention: name the parts of your life and aim.
3. **Systems.** Takes proven goals: focuses with a standard and a review cadence.
4. **Energy.** Takes history: a daily one-tap check-in that later shapes plans. It is cheap to capture early and is shown last.

**Decided for now: the ladder in Settings is two levels, layer 1 and layer 2.** Systems (focuses) and energy stay off the ladder for now. The owner keeps focuses on for himself.

Parked, to decide later:
- **New users start in layer 1** (no areas or goals, which is #109's simple mode). Areas and goals are offered after a few weeks of use, not in onboarding step 3.
- **The Brain offers the next layer when there is evidence**, for example "You've delegated 20 things this month. Want to set goals?" or "Same sales goal three cycles running. Make it a system?" The user doesn't have to find it in Settings.
- **Where Life OS stands against the layers:** layer 2 is the most built. Layer 1, the one that wins a new user in week one, still lacks the waiting pile (#118), delegation and WhatsApp. So the build leans to layer 1 first.

### The Brain page, cleaned up
> "Inbox" title inside Brain; Needs you and Queue › To review are the same thing twice; Captures is not a tab; footer links repeat the tabs. (25 Nov)

Brain gets one title and four tabs: Needs you · Captures (with Filed / Working on it / Failed as chips) · Activity (with the Outbox inside it) · Sources. The footer links go. List tools appear only past about ten rows. "Agent" becomes "the Brain" wherever it means the Brain.

### "Update available" where you can see it
Settings › Advanced › Updates is hard to find. The setup card (bottom left) shows "Update available · Update now" when `main` is ahead of the site.

### Hand a job to your assistant from Life OS
> "no hermes can make changes - why dont you tell hermes to do it." (26 Nov)

Life OS (or Chat) puts a request ("cancel the Twinings meet") in the queue the connector pulls. The assistant does it on its next run and reports back the result. This needs one more kind of change in `agent/connector`.

### WhatsApp: talk to Life OS, forward to it, remind people
> "How can I ingest WhatsApp as a source. Official is not possible." (24 Nov)
> "people may want to talk to lifeos through a whatsapp number - that will drive adoption. so forget it reading. but let it send message reminders to people for delegated tasks and let the user also interact with lifeos via whatsapp. also forwarding information will become easy" (26 Nov)

Decided: Life OS never reads the owner's own WhatsApp chats. It gets a WhatsApp number people talk to.

- **Talk:** the same Chat as in the app ("what's on today", "remind me at 4", "ask Vivek for the ITR draft by Friday").
- **Forward:** a message, voice note, photo or PDF forwarded to the number lands in the Brain and is filed.
- **Hear from it:** the morning brief, "3 things need you", "Vivek's draft is 2 days late" (the owner opts in by adding his number in his profile).
- **Remind people you delegated to:**
  - By default the reminder goes from the owner's own WhatsApp: Life OS drafts it and one tap opens WhatsApp with the text ready (a wa.me link). It is free, needs no opt-in, and people answer the boss's number.
  - Optionally Life OS sends reminders itself, but only after the person opts in: the first message carries "Tap to get reminders about this from Jai's assistant". Meta requires opt-in before a business messages anyone.
- **The official route only:** Meta's WhatsApp Cloud API. No unofficial bridges (Baileys and the like) in the product: they link the whole account, can get the number restricted, and break when WhatsApp updates.
- **Simple first, for the owner:** a second number of his own on the Cloud API, connected straight to his site. Later, for customers: one BTW number, with a small relay that passes each message to the sender's own site. Customers then don't go through Meta's business verification themselves.
- **Cost:** 1,000 free messages a month per number, then ₹0.115 a message before GST (India, from 1 Oct 2026).
- **The owner's steps:** Meta Business verification, a number, display-name approval, about 5 templates (reminder, nudge, morning brief, needs you, opt-in).
- **Build:** a WhatsApp channel and skill next to phone and email, outgoing templates, the one-tap "send from your own WhatsApp" link, and later the relay. After #120 (Chat everywhere).
- **Goes with delegation:** "delegate from a sentence", "spot the reply that closes it" (start with "Looks done · Confirm") and "nudge with a ready follow-up", on top of #118's waiting pile.
- **Meanwhile:** the owner connects Hermes to WhatsApp (bot mode, second number) and talks to Life OS through it.
- **Still useful without the number:** Life OS in the phone's share sheet (partly in #120), and an importer for WhatsApp's "Export chat" (.txt plus media).

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

### Contacts: a directory, and people only when they matter
> "should we create an issue to import contacts into the library - its important no?" … "Contacts could become people only if they are meaningful" (26 Nov)

Google Contacts (read only, daily) and .vcf uploads go into Frappe's `Contact` as a private directory: no pages, no briefs, no AI cost. A contact becomes a `Life Person` when it matters: you replied or met; you named them in a task, capture or Chat; a saved contact writes for real (one sighting is enough, against three for a stranger); starred or in a label you mark. The first import fills in existing people, makes pages for those you've replied to or met in 90 days (one Undo), and asks once about the rest. The directory still names senders, answers "what's Ravi's number", and gets phone numbers ready for WhatsApp. Learns through #117's Change. The full proposal, with tests, is in #122 (closed, parked).

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
- Dashboard at the top of Today › Week, everything in the drawer: #123.
