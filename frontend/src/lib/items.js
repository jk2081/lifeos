// Issue 10: what the Review screen and the item page share about one inbox item.
import { toast } from 'frappe-ui'
import { api, tryCall } from '@/lib/api'
import { refreshCounts } from '@/lib/store'

// Accept or reject every waiting proposal. `reload` fetches the item again and returns it; each proposal the server refused
// keeps its reason on its card. Returns the server's answer, or null when the call failed.
export async function decideAll(item, decision, reload) {
  const res = await tryCall(() => api('review.decide_all', { item: item.name, decision }))
  if (!res) return null
  const fresh = await reload()
  for (const err of res.errors) {
    const p = fresh?.proposals.find((x) => x.name === err.proposal)
    if (p) p.error = err.error
  }
  if (res.errors.length) toast.warning(`${res.decided.length} accepted. ${res.errors.length} still need${res.errors.length === 1 ? 's' : ''} a change.`)
  else toast.success(decision === 'accept' ? `${res.decided.length} accepted.` : `${res.decided.length} rejected.`)
  refreshCounts()
  return res
}
