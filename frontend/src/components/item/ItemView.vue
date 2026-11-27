<template>
  <!-- issue 128: the one Drawer. Its layers are a chat or a record or a list; the top one shows, the ones under it come back with Back -->
  <Drawer :open="!!cur && !(phone && cur.type === 'ask')" :width="cur?.type === 'inbox' ? 760 : undefined">
    <div v-if="cur?.type === 'ask'" class="flex h-full min-h-0 flex-col" role="complementary" aria-label="Chat" data-ask-panel :data-wide="drawer.wide ? 1 : 0" :data-docked="docked ? 1 : 0" data-layer="ask"><AskBody /></div>
    <div v-else-if="cur" ref="el" class="flex h-full min-h-0 flex-col outline-none" role="dialog" :aria-label="meta.title || label" tabindex="-1" data-pane :data-pane-ref="cur.ref" :data-layers="stack.length">
    <header class="flex flex-none flex-col gap-2.5 border-outline-gray-1 px-4 pb-3 md:px-5" :class="[phone ? 'pt-0' : 'pt-3.5', tabs.length > 1 ? '' : 'border-b']">
    <!-- the actions on their own line with Close pinned at the end; the kind and title below at the pane's full width,
         so the title never shares a row with buttons -->
    <div class="flex items-start gap-1.5">
      <!-- issue 128: Back to the layer below (a list, a chat, the record this one was opened from); on a phone a list's own Back is the way to the dashboard, and so is a review's goal or meeting's: back to the review (issue 146) -->
      <Button v-if="stack.length > 1 || (phone && (cur.type === 'list' || cur.type === 'meeting' || route.query.review))" class="shrink-0" :size="btnSize" icon-left="lucide-arrow-left" label="Back" data-pane-back @click="popLayer" />
      <div class="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5" data-pane-actions>
      <Button v-if="!store.isAgent && ASKABLE[cur.type] && !missing" :size="btnSize" icon-left="lucide-sparkles" :label="phone ? 'Chat' : 'Chat about this'" data-pane-ask
        @click="askAbout(ASKABLE[cur.type], cur.name, meta.title)" />
      <!-- the sensitive mark (UX fixes, set 6): a lock while it is on; anyone who may edit marks it, only the space's owner unmarks it -->
      <Button v-if="meta.sensitive && !store.isAgent" :size="btnSize" :icon-left="meta.sensitive.on ? 'lucide-lock' : 'lucide-lock-open'" :variant="meta.sensitive.on ? 'subtle' : 'ghost'"
        :label="phone ? '' : meta.sensitive.on ? 'Sensitive' : 'Mark sensitive'" :tooltip="meta.sensitive.on ? 'Sensitive: follows the Vault rules. Click to unmark (the space owner only).' : 'Mark sensitive'"
        :aria-pressed="meta.sensitive.on" data-pane-sensitive @click="toggleSensitive" />
      <Button v-if="meta.someday" :size="btnSize" icon-left="lucide-clock" :label="phone ? 'Someday' : 'Move to Someday'" data-pane-someday @click="toSomeday" />
      <Button v-if="meta.fullPage" :size="btnSize" label="Open full page" :route="meta.fullPage" data-pane-full />
      </div>
      <Button v-if="!phone" class="shrink-0" :size="btnSize" variant="ghost" :label="drawer.wide ? 'Collapse' : 'Expand'" data-pane-expand @click="drawer.wide = !drawer.wide" />
      <Button class="shrink-0" :size="btnSize" icon="lucide-x" label="Close" tooltip="Close" data-pane-close @click="closePane" />
    </div>
    <div class="min-w-0">
      <!-- issue 83: the item's path inside the pane, the place it lives in first -->
      <div class="text-sm text-ink-gray-6" data-pane-path>{{ place }} / {{ label }}</div>
      <h2 class="break-words text-lg-semibold text-ink-gray-9" data-pane-title>{{ meta.title || (missing ? 'Not found' : 'Loading…') }}</h2>
    </div>
    <div v-if="meta.area || meta.goal || meta.sub" class="flex flex-wrap items-center gap-2">
      <Button v-if="meta.area" size="sm" variant="outline" icon-left="lucide-folder" :label="meta.area_name || 'Area'" :route="`/today?area=${meta.area}`" />
      <Button v-if="meta.goal" size="sm" variant="outline" icon-left="lucide-target" :label="meta.goal_title || meta.goal" data-pane-goal @click="openRef('goal:' + meta.goal)" />
      <span v-if="meta.sub" class="text-sm text-ink-gray-6">{{ meta.sub }}</span>
    </div>
  </header>
  <!-- the pane's own tabs (ptab=), under the header; a pane with one tab shows no bar -->
  <TabBar v-if="tabs.length > 1" class="flex-none" list-class="px-4 md:px-5" :tabs="tabs" :model-value="ptab.current.value"
    :label="label + ' sections'" :level="2" data-pane-tabs @update:model-value="ptab.set" />
  <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-8 pt-4 md:px-5" data-pane-body>
    <Alert v-if="meta.archived" title="This record is archived. It is shown read-only."
      :primary-action="meta.canRestore ? { label: 'Restore', onClick: () => restore() } : undefined" />
    <Card v-if="missing"><EmptyState line="This record was not found. It may be in another space, or it was removed." /></Card>
    <component :is="VIEW[cur.type]" v-else :key="cur.ref + ':' + stamp" :name="cur.name" :type="cur.type" :tab="tabs.length ? ptab.current.value : undefined" @meta="gotMeta" @missing="missing = true"
      @changed="changed()" @close="closePane" />
  </div>
    </div>
  </Drawer>
</template>

<script setup>
// The item view: what one record is, in a header (type, title, filing, buttons) and the content for its kind. Desktop: our
// slide-over from the right, the list still usable beside it. Phone: frappe-ui's BottomSheet. Which record is open lives in
// the URL (lib/pane.js). The inside is defined once and used in both places.
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert, Button } from 'frappe-ui'
import TabBar from '@/components/TabBar.vue'
import Card from '@/components/ui/Card.vue'
import Drawer from '@/components/ui/Drawer.vue'
import AskBody from '@/components/ask/AskBody.vue'
import FocusPane from '@/components/item/FocusPane.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import TaskPane from '@/components/item/TaskPane.vue'
import VaultPane from '@/components/item/VaultPane.vue'
import GoalPane from '@/components/item/GoalPane.vue'
import ChatPane from '@/components/item/ChatPane.vue'
import EntryPane from '@/components/item/EntryPane.vue'
import DayPane from '@/components/item/DayPane.vue'
import NotePane from '@/components/item/NotePane.vue'
import ListPane from '@/components/item/ListPane.vue'
import PersonPane from '@/components/item/PersonPane.vue'
import MeetingPane from '@/components/item/MeetingPane.vue'
import SourcePane from '@/components/item/SourcePane.vue'
import ChangePane from '@/components/item/ChangePane.vue'
import { itemData } from '@/data/item'
import { tryCall } from '@/lib/api'
import { TYPES, closePane, current as cur, openRef, paneNav, popLayer, recordChanged, stack, swapTop } from '@/lib/pane'
import { drawer, isDocked as docked, isPhone as phone } from '@/lib/drawer'
import { useUrlTab } from '@/lib/tabs'
import { park } from '@/lib/someday'
import { ask, askAbout } from '@/lib/ask'
import { store } from '@/lib/store'

const router = useRouter()
const route = useRoute()
const el = ref(null)
const meta = ref({})
const missing = ref(false)
const stamp = ref(0)
// the path names the view the record was opened in: Week / Event, Month / Event (issue 99); Day when it is Day or somewhere else
const CALENDAR_VIEW = { '/today/week': 'Week', '/today/month': 'Month', '/today/year': 'Year' }
const place = computed(() => {
  if (!cur.value) return ''
  const t = TYPES[cur.value.type]
  const path = route.path.replace(/^\/life/, '')
  return t.place === 'Today' ? CALENDAR_VIEW[path] || (path === '/today' ? 'Day' : t.place) : t.place
})
const label = computed(() => (cur.value ? meta.value?.kind || TYPES[cur.value.type].label : ''))
let lastRef = ''
let opener = null

// Each kind of record says its tabs in its meta: [{ value, label, count }]. The open one is ptab= in the URL; the first is the default.
const tabs = computed(() => (missing.value ? [] : meta.value.tabs || []))
// the header's buttons: small beside a desktop pane's title, full size (40 px) to tap on a phone
const btnSize = computed(() => (phone.value ? 'md' : 'sm'))
const ptab = useUrlTab('ptab', tabs, { replace: true, fallback: () => (route.query.focus === 'pending' ? 'decisions' : null) }) // a link to the pending proposals opens on Decisions
// "Ask about this": the record and the records linked to it are the question's scope
const ASKABLE = { task: 'Life Task', note: 'Life Note', goal: 'Life Goal', chat: 'Life Chat Log', source: 'Life Inbox Item',
  inbox: 'Life Inbox Item', vault: 'Life Vault Document' }
const VIEW = { source: SourcePane, change: ChangePane, task: TaskPane, inbox: defineAsyncComponent(() => import('@/components/review/InboxReview.vue')), note: NotePane, vault: VaultPane, goal: GoalPane, chat: ChatPane, event: EntryPane, date: EntryPane, day: DayPane, list: ListPane, person: PersonPane, focus: FocusPane, meeting: MeetingPane }

// where each layer was scrolled to, so Back finds a list as it was left
const scrolls = new Map()
const bodyEl = () => el.value?.querySelector('[data-pane-body]')
function gotMeta(m) {
  meta.value = m
  const ref = cur.value?.ref
  const y = scrolls.get(ref)
  if (y) nextTick(() => { const b = bodyEl(); if (b && cur.value?.ref === ref) b.scrollTop = y; scrolls.delete(ref) })
}
watch(() => cur.value?.ref, async (now, before) => {
  if (before && el.value) scrolls.set(before, bodyEl()?.scrollTop || 0)
  meta.value = {}
  missing.value = false
  if (now && !before) opener = document.activeElement
  if (now) {
    lastRef = now
    await nextTick()
    el.value?.focus({ preventScroll: true })
    document.querySelector(`[data-ref="${CSS.escape(now)}"]`)?.scrollIntoView({ block: 'nearest' })
  } else {
    // focus goes back to the row the pane was opened from
    await nextTick()
    const row = lastRef && document.querySelector(`[data-ref="${CSS.escape(lastRef)}"]`)
    ;(row || (opener && document.contains(opener) ? opener : null))?.focus?.({ preventScroll: true })
  }
}, { immediate: true })

function changed() {
  if (cur.value) recordChanged(cur.value.ref)
}
function reload() {
  stamp.value++
  changed()
}
async function restore() {
  if (await tryCall(() => itemData.archive.restore({ doctype: TYPES[cur.value.type].doctype || 'Life Inbox Item', name: cur.value.name }), 'Restored.')) reload()
}
async function toggleSensitive() {
  const s = meta.value.sensitive
  if (await tryCall(() => itemData.library.set_sensitive({ doctype: s.doctype, name: s.name, sensitive: s.on ? 0 : 1 }), s.on ? 'No longer sensitive.' : 'Marked sensitive.')) reload()
}
async function toSomeday() {
  if (await park(meta.value.someday.doctype, meta.value.someday.name, meta.value.title)) reload()
}
const otherDialog = () => [...document.querySelectorAll('[role="dialog"]')].some((d) => !d.hasAttribute('data-pane') && d.offsetParent !== null)
function step(n) {
  const i = paneNav.rows.indexOf(cur.value.ref)
  const next = paneNav.rows[i + n]
  if (i < 0 || !next) return
  swapTop(next)
}
function onKey(e) {
  if (!cur.value || cur.value.type === 'ask' || e.metaKey || e.ctrlKey || e.altKey) return
  const t = e.target
  if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || (t.closest && t.closest('.cm-editor, [role="listbox"], [role="menu"], [role="combobox"], [role="tablist"], [role="radiogroup"]'))) return
  if (otherDialog()) return
  if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); step(1) }
  else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); step(-1) }
}
const onEsc = () => { if (cur.value && !otherDialog()) popLayer() } // Esc takes one layer off; the last one closes the Drawer

onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('lifeos-escape', onEsc)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('lifeos-escape', onEsc)
})
</script>
