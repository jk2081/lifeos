---
name: channel-gmail
title: Gmail
when_to_use: Mail Life OS reads from a connected Gmail mailbox: the cheap checks first, then whether it matters.
trigger: Served
tools: []
output: Proposals
model: Fast
cost_limit: 0.25
version: 2
---
These are the rules for mail read from Gmail. They come after the shared rules and before the rules of the kind of thing it is.

## What arrives

Mail is not copied into Life OS. Each morning one digest lists the mail from real people, grouped by inbox (on Sundays a second one rolls up the week), each with the sender, the subject, one line and a File it button. Anything else is found by searching the inbox live when the owner or an agent asks, and kept only when the owner says so. Life OS itself only reads; an agent sends, drafts, archives or labels only through the tools the owner switched on.

## Let in

- Mail from real people
- Mail with a bill, a booking or a document in it
- Mail the owner has replied to

## Check every

- Not Promotions, Social, Updates or Forums
- Not a mailing list or a no-reply sender
- The always-include and always-skip lists of the mailbox
- Whether the thread is worth a line in the digest

## Who may send

- A real person, not a system
- Any sender on the mailbox's always-include list

## Where it goes

- The digest is one item; filing a line from it makes the Brain item for that thread
- Mail from the always-sensitive list is marked sensitive

## What to propose

- A task for each request or promise
- A reply task when the owner is expected to answer
- A date for a booking

## Never

- Do not reply, mark, label, move or delete mail on your own: an act goes through the agent tools, and the owner's switches decide
- Do not list bulk mail that slipped through the filters

## Examples

- A school asking for a form by Friday: keep, and a task with that date
- A shop's weekly offer: skip

## Lessons from the owner's corrections
