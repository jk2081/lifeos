import { call, toast } from 'frappe-ui'

// Every server call goes through here. Methods live under lifeos.api.
export function api(method, args = {}) {
  const path = method.startsWith('frappe.') ? method : `lifeos.api.${method}`
  const out = call(path, args)
  // the sidebar's counts (items to review, tasks due) follow any change that can move them, without a reload
  if (CHANGES.test(method)) out.then(() => window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))).catch(() => {})
  return out
}
const CHANGES = /^(tasks\.(set_status|update|quick_add|carry_forward)|archive\.|inbox\.|review\.|chats\.make_task|journal\.(month_plan_make_task|decide))/

export function errorText(e) {
  const messages = e?.messages || e?.exc_messages
  let text = (Array.isArray(messages) && messages[0]) || e?.message || String(e)
  return String(text).replace(/<[^>]+>/g, '')
}

// Run an optimistic change: apply it at once, undo it and say why if the server refuses.
export async function optimistic(apply, undo, request) {
  apply()
  try {
    return await request()
  } catch (e) {
    undo()
    toast.error(errorText(e))
    throw e
  }
}

export async function tryCall(fn, okMessage) {
  try {
    const out = await fn()
    if (okMessage) toast.success(okMessage)
    return out
  } catch (e) {
    toast.error(errorText(e))
    return undefined
  }
}

export const db = {
  insert: (doc) => call('frappe.client.insert', { doc }),
  set: (doctype, name, values) => call('frappe.client.set_value', { doctype, name, fieldname: values }),
  delete: (doctype, name) => call('frappe.client.delete', { doctype, name }),
  get: (doctype, name) => call('frappe.client.get', { doctype, name }),
}
