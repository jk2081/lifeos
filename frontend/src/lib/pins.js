// The person's pinned pages (issue 111): at most seven, in the order they chose, shown in the sidebar under Library and, on a phone, at the top of
// the Library tab. One list for the whole app; a page, the sidebar and the phone all read it. Pinning, unpinning and dragging call the server and
// take the list it answers with.
import { reactive } from 'vue'
import { libraryData } from '@/data/library'
import { tryCall } from './api'

export const pins = reactive({ list: [], limit: 7, loaded: false })

// the kind icons: company, person, part or project, note
export const KIND_ICON = { company: 'lucide-building-2', person: 'lucide-user', part: 'lucide-layers', note: 'lucide-file-text' }
// what a line of a timeline is
export const ITEM_ICON = { Email: 'lucide-mail', Capture: 'lucide-inbox', Task: 'lucide-circle-check', Meeting: 'lucide-calendar', Note: 'lucide-file-text', Chat: 'lucide-message-square' }

export const pagePath = (doctype, name) => `/library/pages/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`

const take = (res) => {
  if (res?.pins) pins.list = res.pins
  return res
}

export async function loadPins() {
  const res = await tryCall(() => libraryData.pages.pinned())
  if (res) { pins.list = res.pins; pins.limit = res.limit; pins.loaded = true }
}

export const isPinned = (doctype, name) => pins.list.some((p) => p.doctype === doctype && p.name === name)

/** Pin a page. With seven pinned the server answers `refused` and `choose_to_unpin`: the caller asks which to drop and calls again with `replace`. */
export async function pin(doctype, name, replace) {
  return take(await tryCall(() => libraryData.pages.pin({ doctype, name, replace })))
}
export async function unpin(doctype, name) {
  return take(await tryCall(() => libraryData.pages.unpin({ doctype, name })))
}
export async function reorder(order) {
  pins.list = order.map((r) => pins.list.find((p) => `${p.doctype}:${p.name}` === r)).filter(Boolean) // at once, then what the server says
  return take(await tryCall(() => libraryData.pages.reorder({ order })))
}
