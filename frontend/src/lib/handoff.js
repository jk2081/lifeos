// What the owner does with a waiting item (issue 130): Confirm a reply that looks like the answer, Not yet, Nudge. One place, so the Waiting list, Needs you, the
// weekly review and the task layer do the same thing. Nothing is sent here: a nudge makes a draft (email) or a WhatsApp link, and the owner sends it.
import { toast } from 'frappe-ui'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { openRef, recordChanged } from '@/lib/pane'

export async function confirmDone(task, title) {
  const out = await tryCall(() => itemData.tasks.looks_done_confirm({ task }), title ? `Done: ${title}.` : 'Done.')
  if (out) recordChanged()
  return out
}

export async function notYet(task) {
  const out = await tryCall(() => itemData.tasks.looks_done_not_yet({ task }), 'Still waiting.')
  if (out) recordChanged()
  return out
}

// Nudge: a two-line follow-up the way the hand-off went. WhatsApp opens its link (the phone comes from the person's page); an email is a draft on the task, with Send.
export async function nudge(task, channel) {
  const out = await tryCall(() => itemData.tasks.nudge({ task, channel }))
  if (!out) return null
  recordChanged()
  if (out.channel === 'whatsapp' && out.whatsapp) window.open(out.whatsapp, '_blank', 'noopener,noreferrer')
  else if (out.channel === 'whatsapp') toast.info('Add their phone number on the task to open WhatsApp.')
  openRef('task:' + task, { push: true })  // on top of the list it was made from, with Back
  return out
}

export async function nudgeDecide(task, to) {
  const out = await tryCall(() => itemData.tasks.nudge_decide({ task, to }), { week: 'Waiting a week more.', plate: 'Back on your plate.', drop: 'Dropped.' }[to])
  if (out) recordChanged()
  return out
}

export const initials = (name) => (name || '?').replace(/\(.*\)/, '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'
