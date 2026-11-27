<template>
  <ListView ref="list" title="Library" sub="Everything you know, kept and searchable. Filed here by you or by the Brain." noun="items" :screen="'library-' + tab" doctype="Life Index" mode="feed"
    :spec="SPEC" :quick="['goal', 'source_system']" :virtual="VIRTUAL" :only="['goal']" :sortable="false" :groupable="false" :watch-keys="['q']" :fetch="fetch"
    :row-ref="(r) => (r.doctype === 'Life Person' ? `person:${r.name}` : r.ref)" :row-key="(r) => r.ref" :row-label="(r) => r.title"
    empty-title="Nothing kept yet." empty-hint="Notes, documents, people and chats you keep, or the Brain files for you, will show up here."
    :empty-action="writable ? { label: 'Chat', icon: 'lucide-message-square', click: () => openChat() } : null" @loaded="onLoaded">
    <template #above>
      <div class="flex flex-wrap items-center gap-2" data-library-everything data-lib-filters :data-lib-tab="tab" :data-loaded="loaded ? 1 : 0">
        <TextInput v-model="q" class="w-full min-w-0 sm:w-80" type="search" :placeholder="`Search ${PLACEHOLDER[tab] || 'the Library'}...`" aria-label="Search the Library" data-lib-search @keydown.enter="applyQuery" />
        <Button :variant="unopened ? 'solid' : 'subtle'" :label="`Not opened in 90 days${numbers ? ' ' + numbers.notes_unopened.n : ''}`" :aria-pressed="unopened" data-lib-unopened
          @click="router.replace({ query: { ...route.query, unopened: unopened ? undefined : 1 } })" />
        <span v-if="numbers" class="text-sm text-ink-gray-6" data-lib-numbers>Notes and sources <b class="tabular-nums text-ink-gray-9" data-lib-number="notes_sources">{{ numbers.notes_sources.n.toLocaleString() }}</b></span>
      </div>
    </template>
    <template #row="{ row: r }">
      <div class="flex min-w-0 flex-col gap-1 md:grid md:grid-cols-[2rem_minmax(0,1fr)_minmax(0,16rem)_4.5rem] md:items-center md:gap-4" data-lib-row :data-ref="r.ref" :data-kind="r.kind" :data-letter="r.letter">
        <div class="flex min-w-0 items-start gap-3 md:contents">
          <span class="flex size-8 flex-none items-center justify-center rounded-md text-sm-medium" :class="LETTER_CLASS[r.letter]" aria-hidden="true" data-lib-letter>{{ r.letter }}</span>
          <div class="min-w-0 flex-1">
            <div class="break-words text-base-medium text-ink-gray-9" data-lib-title>{{ r.title }}</div>
            <div class="break-words text-sm text-ink-gray-6" data-lib-line>{{ r.line }}<span v-if="r.sensitive" role="img" aria-label="Sensitive" data-sensitive-lock> 🔒</span>
              <Badge v-if="r.expiry" class="ml-1" size="sm" :theme="r.expiry.state === 'expired' ? 'red' : 'amber'" :label="r.expiry.state === 'expired' ? 'Expired' : `Expires in ${r.expiry.days} days`" data-expiry-badge /></div>
          </div>
        </div>
        <div class="min-w-0 truncate pl-11 text-sm text-ink-gray-7 md:pl-0 md:text-base" data-lib-where>{{ [r.area_name, r.goal_title].filter(Boolean).join(' · ') }}</div>
        <div class="whitespace-nowrap pl-11 text-sm text-ink-gray-6 md:pl-0 md:text-right" data-lib-date>{{ short(r.date) }}</div>
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { openChat } from '@/lib/ask'
// Library > Everything (issue 23): notes, documents, people and chats in one list, newest first. Each row has a kind letter (N, P, D, C), a title, a line about it,
// its area and goal, and a date. It is the shared list (ListView): the area is the lens, Goal and Source are filters of the shared bar, "Not opened in 90 days" a
// switch, and all of them live in the address (area, goal, source, unopened) as on every list. The search box reads titles and bodies (q). Sensitive items follow the Vault's rules on the server.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, TextInput } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import { libraryData } from '@/data/library'
import { tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'

const props = defineProps({ tab: { type: String, default: 'all' } })
const route = useRoute()
const router = useRouter()
const PLACEHOLDER = { all: 'notes, documents, people, chats', people: 'people' }
const LETTER_CLASS = { N: 'bg-surface-gray-2 text-ink-gray-7', P: 'bg-surface-blue-2 text-ink-gray-9', D: 'bg-surface-amber-2 text-ink-gray-9', C: 'bg-surface-violet-1 text-ink-violet-8' }
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'goal', field: 'goal', kind: 'link' }, { key: 'source', field: 'source_system', kind: 'value' }, { key: 'unopened', kind: 'flag' }]
const VIRTUAL = [{ fieldname: 'goal', label: 'Goal', fieldtype: 'Link', options: 'Life Goal' }, { fieldname: 'source_system', label: 'Source', fieldtype: 'Data' }]
const numbers = ref(null)
const loaded = ref(false)
function onLoaded(res) {
  loaded.value = true
  if (res.numbers) numbers.value = res.numbers
}
const q = ref(route.query.q || '')
const writable = computed(() => canWrite())
// the old Open band's note numbers (issue 55): "Not opened in 90 days" is a switch of the list (the flag `unopened`) with its own count
const unopened = computed(() => route.query.unopened === '1' || route.query.unopened === 1)

const applyQuery = () => router.replace({ query: { ...route.query, q: q.value.trim() || undefined } })
let timer
watch(q, () => { clearTimeout(timer); timer = setTimeout(applyQuery, 300) })
watch(() => route.query.q, (v) => { if ((v || '') !== q.value.trim()) q.value = v || '' })

async function fetch({ params: p, start, page_length }) {
  const [res, counts] = await Promise.all([
    tryCall(() => libraryData.everything.list({ space: store.space, tab: props.tab, q: route.query.q || undefined, area: p.area || undefined, goal: p.goal || undefined,
      source: p.source || undefined, unopened: p.unopened ? 1 : undefined, start, page_length })),
    start ? null : tryCall(() => libraryData.counts.get({ space: store.space, which: 'library', area: p.area || undefined })),
  ])
  if (!res) return null
  return { ...res, numbers: counts || undefined }
}
</script>
