<template>
  <CommandPalette v-model:open="open" v-model:query="text" :filterable="false" title="Search or ask" @select="go">
    <CommandPaletteInput ref="field" placeholder="Search or ask anything" aria-label="Search or ask anything" />
    <CommandPaletteList>
      <!-- Ask (UX fixes, set 5): first when the text reads as a question, so Enter asks; last otherwise -->
      <CommandPaletteItem v-if="askFirst" :value="ASK" :label="'Ask: ' + text" data-search-ask>
        <div class="flex min-w-0 items-center gap-2 py-0.5"><span class="lucide-sparkles size-4 text-ink-gray-7" aria-hidden="true" />
          <span class="truncate text-base-medium text-ink-gray-9">Ask: {{ text.trim() }}</span></div>
        <template #suffix><Badge theme="blue" :label="askScopeLabel" /></template>
      </CommandPaletteItem>
      <CommandPaletteItem v-for="r in results" :key="r.ref_name + r.kind" :value="r" :label="r.title || 'Untitled'" data-search-hit>
        <div class="flex min-w-0 flex-col gap-0.5 py-0.5">
          <span class="truncate text-base-medium text-ink-gray-9">{{ r.title || 'Untitled' }}</span>
          <span class="truncate text-sm text-ink-gray-6">{{ [multi && r.space, r.area_name, short(r.record_date, true), r.is_archived ? 'archived' : ''].filter(Boolean).join(' · ') }}</span>
          <span v-if="r.snippet" class="truncate text-sm text-ink-gray-6">{{ r.snippet }}</span>
        </div>
        <template #suffix><Badge :label="KIND[r.kind] || r.kind" /></template>
      </CommandPaletteItem>
      <CommandPaletteItem v-if="text.trim() && !askFirst" :value="ASK" :label="'Ask: ' + text" data-search-ask>
        <div class="flex min-w-0 items-center gap-2 py-0.5"><span class="lucide-sparkles size-4 text-ink-gray-7" aria-hidden="true" />
          <span class="truncate text-base-medium text-ink-gray-9">Ask: {{ text.trim() }}</span></div>
        <template #suffix><Badge theme="blue" :label="askScopeLabel" /></template>
      </CommandPaletteItem>
    </CommandPaletteList>
    <CommandPaletteEmpty>
      <Empty v-if="searched" :title="`Nothing found for “${searched}”.`" :hint="`Try fewer words${archived ? '' : ', or include archived records'}.`" />
      <Empty v-else title="Search everything you can see." hint="Type a word from a title, a note or a transcript." />
    </CommandPaletteEmpty>
    <CommandPaletteFooter>
      <div class="flex w-full flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <Checkbox v-model="archived" label="Include archived" />
          <!-- Ask's own page (threads and insights) left the sidebar in set 6: it is reached from here and from Today -->
          <Button size="sm" variant="ghost" icon-left="lucide-history" label="History" data-search-history @click="toAsk('history')" />
          <Button size="sm" variant="ghost" icon-left="lucide-lightbulb" label="Insights" data-search-insights @click="toAsk('insights')" />
        </div>
        <span class="flex items-center gap-1 text-sm text-ink-gray-6"><KeyboardShortcut bg combo="ArrowUp" use-icons /><KeyboardShortcut bg combo="ArrowDown" use-icons /> to move,
          <KeyboardShortcut bg combo="Enter" use-icons /> to open<template v-if="askFirst">, or to ask</template></span>
      </div>
    </CommandPaletteFooter>
  </CommandPalette>
</template>
<script setup>
// Search over everything the person can see. frappe-ui's experimental CommandPalette draws it; the results come from
// our own search method, which applies the space rules. A result opens in the pane over the screen you are on.
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Checkbox, KeyboardShortcut } from 'frappe-ui'
import { CommandPalette, CommandPaletteEmpty, CommandPaletteFooter, CommandPaletteInput, CommandPaletteItem, CommandPaletteList } from '@/experimental'
import Empty from './Empty.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { openRef, refOf } from '@/lib/pane'
import { isQuestion, scopeFromRoute, startAsk } from '@/lib/ask'

const open = defineModel('open', { type: Boolean, default: false })
const KIND = { Inbox: 'Inbox item' }
const router = useRouter()
const text = ref('')
const field = ref(null)
const results = ref([])
const searched = ref('')
const archived = ref(false)
const multi = computed(() => store.spaces.length > 1)
const ASK = { ask: true, ref_name: '__ask', kind: 'ask' }
const askFirst = computed(() => isQuestion(text.value) && !store.isAgent)
const askScopeLabel = computed(() => (open.value ? scopeFromRoute().label : ''))
let timer = null
let seq = 0

async function run() {
  const q = text.value.trim()
  if (!q) {
    results.value = []
    searched.value = ''
    return
  }
  const mine = ++seq
  try {
    const res = await api('search.query', { text: q, limit: 20, include_archived: archived.value ? 1 : 0, ...(store.lensArea ? { space: store.space, area: store.lensArea } : {}) })
    if (mine !== seq) return
    results.value = res.results
    searched.value = q
    highlightFirst()
  } catch (e) {
    results.value = []
  }
}
// The palette puts the keyboard on the first row when the query changes, which is before a server search has answered.
// An input event on its field makes it do so again once the rows are drawn, so Enter opens the first result.
async function highlightFirst() {
  await nextTick()
  field.value?.$el?.querySelector('input')?.dispatchEvent(new Event('input', { bubbles: true }))
}
watch([text, archived], () => {
  clearTimeout(timer)
  timer = setTimeout(run, 180)
})
watch(open, (on) => { if (!on) { results.value = []; searched.value = '' } })
function toAsk(tab) {
  open.value = false
  router.push({ path: '/ask', query: { tab } })
}
function go(r) {
  if (!r) return
  if (r.ask) {
    const q = text.value.trim()
    open.value = false
    text.value = ''
    return startAsk(q)
  }
  if (r.space && r.space !== store.space) Object.assign(store, { space: r.space, lensArea: '' }) // a result in another space: its whole space
  if (r.ref_doctype === 'Life Inbox Item') return router.push(r.route) // a capture opens its item page (issue 10)
  const ref = refOf(r.ref_doctype, r.ref_name)
  ref ? openRef(ref) : router.push(r.route)
}
</script>
