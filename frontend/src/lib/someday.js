// Someday (UX fixes, set 5): park, bring back, keep and purge, shared by the Someday screen, Reset, the panes and Ask.
// Each change calls lifeos.api.someday with the person's own permissions; parking shows a toast with Undo for a minute.
import { reactive } from 'vue'
import { dialog, toast } from 'frappe-ui'
import { api, errorText } from './api'
import { recordChanged } from './pane'

export const UNDO_MS = 60000
export const REF_TYPE = { 'Life Task': 'task', 'Life Goal': 'goal', 'Life Note': 'note' }

function changed(doctype, name) {
  recordChanged(`${REF_TYPE[doctype]}:${name}`)
  window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
}

/** Park one task, goal or note (a long-term goal takes its open tasks); a toast offers Undo for a minute. */
export async function park(doctype, name, title = '') {
  try {
    const res = await api('someday.park', { doctype, name })
    changed(doctype, name)
    toast.success(`${title || 'It'} is on the Someday list.`, { duration: UNDO_MS, action: { label: 'Undo', onClick: () => undo(res.undo, doctype, name) } })
    return res
  } catch (e) {
    toast.error(errorText(e))
    return null
  }
}
export async function undo(snapshot, doctype, name) {
  try {
    await api('someday.undo', { snapshot })
    changed(doctype, name)
    toast.success('Undone.')
  } catch (e) { toast.error(errorText(e)) }
}

// The Bring back dialog: what makes the item live again, by type (NewRecord fields)
export const bringBack = reactive({ open: false, row: null, fields: [], initial: {} })
export function askBringBack(row, cycles = []) {
  const f = {
    'Life Task': [{ name: 'due_date', label: 'Due date (optional)', type: 'date', help: 'Leave empty for a task with no date.' }],
    'Life Goal': [{ name: 'target_date', label: 'Target date', type: 'date' },
      { name: 'status', label: 'Status (long-term goals)', options: ['Active', 'On Hold'] },
      ...(cycles.length ? [{ name: 'cycle', label: '12 Week Year (for a 12 Week Year goal)', options: cycles.map((c) => ({ label: c.title, value: c.name })) }] : [])],
    'Life Note': [],
  }[row.doctype]
  Object.assign(bringBack, { open: true, row, fields: f, initial: row.doctype === 'Life Goal' ? { status: 'Active' } : {} })
}
export async function doBringBack(values) {
  const row = bringBack.row
  const res = await api('someday.bring_back', { doctype: row.doctype, name: row.name, ...values })
  changed(row.doctype, row.name)
  toast.success(`${row.title} is back.`)
  return res
}

export async function keep(row) {
  try {
    const res = await api('someday.keep', { doctype: row.doctype, name: row.name })
    changed(row.doctype, row.name)
    toast.success(`Kept until ${res.review_on}.`)
    return res
  } catch (e) { toast.error(errorText(e)) }
}

/** Purge moves the item to the trash, after a confirmation. Resolves true when it was purged. */
export function purge(row) {
  return new Promise((resolve) => {
    dialog.danger({
      title: `Purge ${row.title}?`, confirmLabel: 'Purge',
      message: `It moves to the trash${row.doctype === 'Life Goal' && row.tasks ? ` with its ${row.tasks} parked task${row.tasks === 1 ? '' : 's'}` : ''}. Restore it from Archive, Trash, within 30 days.`,
      onConfirm: async () => {
        await api('someday.purge', { doctype: row.doctype, name: row.name })
        changed(row.doctype, row.name)
        toast.success('Moved to the trash.')
        resolve(true)
      },
      onCancel: () => resolve(false),
    })
  })
}
