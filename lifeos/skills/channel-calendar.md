---
name: channel-calendar
title: Google Calendar
when_to_use: Meetings and events Life OS reads from Google Calendar.
trigger: Served
tools: []
output: Proposals
model: Fast
cost_limit: 0.25
version: 1
---
These are the rules for the calendar. They come after the shared rules.

## What arrives

Events and meetings from a connected Google Calendar, read only. They are not captures: they show in Today and the calendar views, and meetings come into the review.

## Let in

- Meetings and events with other people
- All-day events such as holidays and trips
- Birthdays and anniversaries

## Check every

- That the event is not a copy of one already on the calendar
- That a change of time replaces the old event

## Who may send

- The owner's own calendars that are switched on in Brain, Sources

## Where it goes

- Today and the calendar views
- A meeting's follow-ups go to the area of the people in it

## What to propose

- A date for a birthday or an anniversary that repeats
- A follow-up task only when the owner promised something in the meeting

## Never

- Do not change, accept or delete an event
- Do not turn every meeting into a task

## Examples

- A dentist appointment: only the calendar, no task
- A client meeting where the owner promised a quote: a task for the quote

## Lessons from the owner's corrections
