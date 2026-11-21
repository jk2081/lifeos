# Life OS: the product direction (from 20 November 2026)

This file is the target design from 20 November 2026 onwards. Where it differs from `SPEC.md` or the "target design" paragraph in `ROADMAP.md`, this file wins. Where a GitHub issue differs from this file, the issue wins. Mockups for it are in `mockups/v2/` (PNG plus the HTML each was rendered from in `mockups/v2/source/`).

## Who it is for

Life OS should work for someone who has never used an AI agent. Until now it was built for one owner who knows the system. From now on, every screen should make sense to a new user on day one, and grow with them.

## How it works: Sources → Brain → Plan

1. **Sources.** Everything that comes in: things you drop in, email, calendar, chats with AI tools, agents such as Hermes, voice notes.
2. **The Brain.** It reads what comes in, files it, and asks you only about what needs a decision (**Needs you**). Anything it could not place goes to an unfiled bucket in Needs you, never lost.
3. **The Plan.** Goals and tasks, organised by the areas of your life, and the calendar.

Board: `mockups/v2/01-how-it-works.png`.

## Navigation

| Place | What it holds | Tabs |
| --- | --- | --- |
| **Today** | The day's plate and the calendar | Day · Week · Month · Year |
| **Brain** | What came in and what the Brain did with it | Needs you · Activity · Sources · Skills (from level 5) |
| **Goals** | Goals and tasks by area, and the plans that pace them | By area · All tasks · No goal · Cycles (the 12 Week Year and the month plan, #45) |
| **Library** | Everything kept | Everything · Notes · Documents · People · Chats · Files (Files is added by its own issue; it is not in the mockup) |
| **Review** | The weekly review (set 8's shell) | Hidden until the first review is due; then it appears |
| **Settings** | As now | |

Brain → Needs you replaces the Inbox. Housekeeping pages (Archive, Outbox, Graph, Timeline, Reset, Vault and the like) leave the sidebar. They are reached from the place they belong to (for example the Outbox from Brain → Activity, the trash from Library) or from Settings → Data.

Phone: a bottom bar with Today, Brain, Goals and Library, and a capture button.

## Areas of life

- Seven areas: **Career, Health, Relationships, Money, Emotions, Mind, Environment.** Each can be switched on or off in Settings → Areas. Career and Health are on by default.
- An area can have **parts**: the owner's businesses (Business That Works, Tea & Coffee) are parts of Career. Parts are `Life Area` rows with `parent_area` set.
- **Every task has an area.** A goal is optional. When a task has no area, the Brain guesses one and shows its guess for the owner to confirm or change.

## Focuses: ongoing work behind the goals

Some things are never "done": improving systems at RMT, marketing at BTW, Ghillidary's yield. They are ongoing bodies of work with a **standard** to keep up and **principles** to work within. A **focus** holds that; goals of any length (12 weeks, a year, three years) serve it for a while and then finish. A focus lives in an area or part, has no "Done when", and is optional: goals without a focus sit directly under their area. Mockups: `mockups/v2/18-goals-focuses.png` and `19-focus.png`.

## The ladder

Six levels of adoption, so a new user is not shown everything at once. Each level opens when the one before it is in use. It teaches working with agents one step at a time. The sidebar shows "Your setup · level n of 6" and the next step.

1. **Task app:** add tasks, capture by voice. Useful on day one, with no AI.
2. **Connect a source:** email or calendar. Tasks appear on their own.
3. **Describe your life:** three to five areas, a few goals. Things file themselves.
4. **Weekly rhythm:** a 30-minute review. You plan around goals. Review joins the menu after the first one.
5. **Give an agent work:** Hermes, OpenClaw or the built-in Brain. Work is done and filed back. Brain → Skills appears.
6. **Delegate:** agents and people, with rights. A system that runs.

## One job, one item

- When an agent does a piece of work (a deck from three files, an analysis), it is **one item** in Life OS with its inputs, outputs, summary and proposals, filed with **one call**. Filing the same job twice updates it.
- **Files are stored once.** The same file (same content hash) is never stored twice; a newer version of the same asset replaces the old one and keeps its history.
- Library → Files shows every file once, with where it is used. Library → People shows people and organisations.

## Skills and the harness

- A harness is everything around a model that makes it useful: context, tools, rules, memory, a loop, and feedback. Life OS is the substrate under any harness: it holds the context, the rules and the memory.
- **Skills** (how to file a deck, how to run the weekly review) are stored in Life OS and served to any harness that connects. When the owner corrects the Brain, the correction becomes a **lesson** in the skill.
- The **built-in Brain** does this work inside Life OS with the owner's own AI key, so a new user needs no outside agent.

## Surfaces

Capture anywhere, decide in the app. Capture from the phone, the desktop, Telegram or WhatsApp (through agents), email, and voice, including Indian languages. Decisions (accepting proposals, planning) happen in the Life OS app. A native phone wrapper comes later.
