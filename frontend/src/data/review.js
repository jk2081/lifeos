// Every server call the review screens make (the weekly, monthly and 12-week reviews, the review of one inbox item, and the
// goal drawer). A component calls these, never `api(` directly. Each call is a frappe-ui resource; a failed call rejects with
// the server's error, so a screen wraps it in tryCall where it shows the message.
import { createResource } from 'frappe-ui'
import { queryParams } from '@/lib/api'
import GET_METHODS from '@/lib/getMethods.json'

const GET = new Set(GET_METHODS)
// the sidebar's counts follow any change that can move them (same rule as lib/api.js)
const CHANGES = /^(archive\.|inbox\.|review\.|periodic\.|weekly\.settle_stale)/

function run(method, args = {}) {
  const url = `lifeos.api.${method}`
  const get = GET.has(url)
  const resource = createResource({ url, method: get ? 'GET' : 'POST', makeParams: get ? queryParams : undefined })
  const out = resource.submit(args)
  if (CHANGES.test(method)) out.then(() => window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))).catch(() => {})
  return out
}

const call = (ns, name) => (args = {}) => run(`${ns}.${name}`, args)

// the weekly review (`weekly.*`) and the monthly and 12-week reviews (`periodic.*`) answer the same methods in the same shape
export const reviewData = {
  weekly: (method, args) => run(`weekly.${method}`, args),
  periodic: (method, args) => run(`periodic.${method}`, args),
  due: call('periodic', 'due'),
  inbox: { get: call('inbox', 'get'), retry: call('inbox', 'retry') },
  goals: { goal_readings: call('goals', 'goal_readings'), update: call('goals', 'update') },
}
