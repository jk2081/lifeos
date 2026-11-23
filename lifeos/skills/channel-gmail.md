---
name: channel-gmail
title: Gmail
when_to_use: Mail Life OS reads from a connected Gmail mailbox: the cheap checks first, then whether it matters.
trigger: Served
tools: []
output: Proposals
model: Fast
cost_limit: 0.25
version: 1
---
These are the rules for mail read from Gmail. They come after the shared rules and before the rules of the kind of thing it is.

## What arrives

Threads from a connected mailbox, read only, every 15 minutes. Life OS never marks, labels, moves or deletes mail.

## Let in

- Mail from real people
- Mail with a bill, a booking or a document in it
- Mail the owner has replied to

## Check every

- Not Promotions, Social, Updates or Forums
- Not a mailing list or a no-reply sender
- The always-include and always-skip lists of the mailbox
- Whether the thread is worth a capture

## Who may send

- A real person, not a system
- Any sender on the mailbox's always-include list

## Where it goes

- Mail kept goes to Needs you, or is filed on its own when it is sure enough
- Mail from the always-sensitive list is marked sensitive

## What to propose

- A task for each request or promise
- A reply task when the owner is expected to answer
- A date for a booking

## Never

- Do not reply, mark, label, move or delete mail
- Do not keep bulk mail that slipped through the filters

## Examples

- A school asking for a form by Friday: keep, and a task with that date
- A shop's weekly offer: skip

## Lessons from the owner's corrections
