// The one way a data module makes a server call: a frappe-ui resource, GET for the methods in getMethods.json and POST for the
// rest. A failed call rejects with the server's error, so a screen wraps it in tryCall where it shows the message. The sidebar's
// counts follow any change that can move them (the same rule as lib/api.js).
import { createResource } from 'frappe-ui'
import { CHANGES, queryParams } from '@/lib/api'
import GET_METHODS from '@/lib/getMethods.json'

const GET = new Set(GET_METHODS)

export function call(ns, name) {
  const method = `${ns}.${name}`
  const url = `lifeos.api.${method}`
  const get = GET.has(url)
  return (args = {}) => {
    const resource = createResource({ url, method: get ? 'GET' : 'POST', makeParams: get ? queryParams : undefined })
    const out = resource.submit(args)
    if (CHANGES.test(method)) out.then(() => window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))).catch(() => {})
    return out
  }
}

export const group = (ns, names) => Object.fromEntries(names.map((name) => [name, call(ns, name)]))
