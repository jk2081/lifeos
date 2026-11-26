<template>
  <!-- the notes as a list, on the cross-type index: /library/notes?view=list, and the Notes tab of the goal page -->
  <ListView ref="list" :title="embed ? null : 'Notes'" noun="notes" :screen="embed ? embed.screen + (collection === 'Wiki' ? '-wiki' : '-notes') : 'library'" :fixed="embed?.fixed" :active="embed ? embed.active : true" doctype="Life Index" :spec="SPEC" :flag-labels="embed?.fixed?.goal ? { archived: 'Include archived' } : { archived: 'Include archived', reference: 'Reference only' }" :quiet="['archived']"
    :virtual="VIRTUAL" :hidden="HIDDEN" :quick="['title', 'area', 'goal']" :fetch="fetchList" :row-ref="(r) => 'note:' + r.name" :watch-keys="embed ? [] : ['by']"
    :empty-title="collection === 'Wiki' ? 'No wiki pages here yet.' : 'No notes yet.'"
    :empty-hint="collection === 'Wiki' ? 'The agent writes wiki pages from the sources you add with Add to wiki.' : 'Notes hold reference material and notes on your goals, in Markdown. Add one with New note.'">
    <template #sub>{{ by === 'assistant' ? 'Notes the assistant keeps from your sources' : by === 'me' ? 'Notes you wrote' : 'Every note' }}{{ inSpace }}</template>
    <template #actions><slot name="actions" /></template>
    <!-- the rules the assistant follows, pinned at the top of its notes -->
    <template v-if="by === 'assistant' && rules" #above>
      <Card flush data-notes-rules><Row :pane="'note:' + rules" label="Rules for the assistant"><span class="lucide-pin size-4 text-ink-gray-6" aria-hidden="true" />
        <div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">Rules for the assistant</div>
          <div class="text-sm text-ink-gray-6">Read before it writes. People edit this page; agents cannot.</div></div></Row></Card>
    </template>
    <template #cell-title="{ row }"><span class="flex min-w-0 flex-wrap items-center gap-2"><span v-if="row.vault_locked" class="lucide-lock size-3.5 text-ink-gray-6" role="img" aria-label="Sensitive" data-sensitive-lock />
      <span class="break-words font-medium text-ink-gray-9">{{ row.title }}</span>
      <Badge v-if="row.collection === 'Wiki'" size="sm" theme="blue" label="Kept by the assistant" data-assistant-badge /></span></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="{ query: { ...$route.query, area: row.area, open: undefined } }">{{ row.area_name }}</RouterLink></template>
    <template #cell-goal="{ row }"><RefLink v-if="row.goal" class="relative truncate text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="`goal:${row.goal}`" data-note-goal>{{ row.goal_title }}</RefLink></template>
    <template #cell-record_date="{ row }"><span class="whitespace-nowrap">{{ short(row.record_date || row.modified, true) }}</span></template>
    <template #cell-kind="{ row }"><span class="truncate">{{ row.kind || 'Note' }}</span></template>
    <template #stack="{ row }"><div class="flex flex-wrap items-center gap-2"><span v-if="row.vault_locked" class="lucide-lock size-3.5 text-ink-gray-6" role="img" aria-label="Sensitive" />
      <span class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</span><Badge v-if="row.collection === 'Wiki'" size="sm" theme="blue" label="Kept by the assistant" /></div>
      <div class="text-sm text-ink-gray-6">{{ [row.area_name, row.goal_title, 'edited ' + short(row.modified, true)].filter(Boolean).join(' · ') }}</div></template>
  </ListView>
</template>
<script setup>
import RefLink from '@/components/ui/RefLink.vue'
import { libraryData } from '@/data/library'
import { inSpace } from '@/lib/lens'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Badge } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'

// inside a record page's tab (the goal page): { screen, space, fixed: { goal }, active(route) }
// collection: My notes, Wiki (the assistant's notes) or all
const props = defineProps({ embed: { type: Object, default: null }, collection: { type: String, default: 'My notes' } })
const route = useRoute()
const list = ref(null)
// Library > Notes (UX fixes, set 6): every note, with "Written by" me (My notes) or the assistant (the Wiki before set 6)
const by = computed(() => (props.embed ? '' : ['me', 'assistant'].includes(route.query.by) ? route.query.by : ''))
const collectionOf = () => (by.value === 'assistant' ? 'Wiki' : by.value === 'me' ? 'My notes' : props.collection)
const rules = ref('')
onMounted(async () => {
  if (!props.embed && props.collection === 'all') rules.value = (await libraryData.wiki.overview({ space: store.space }).catch(() => ({})))?.rules || ''
})
// the short URL parameters of the list (lib/filterUrl.js). reference=1 is "Reference only": notes with no goal
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'goal', field: 'goal', kind: 'link' },
  { key: 'reference', kind: 'flag' }, { key: 'archived', kind: 'flag' }]
const VIRTUAL = [{ fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' }, { fieldname: 'goal', label: 'Goal', fieldtype: 'Link', options: 'Life Goal' }]
const HIDDEN = ['ref_doctype', 'ref_name', 'kind', 'search_text', 'also_in_csv', 'status', 'record_owner', 'vault_locked']
async function fetchList({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await libraryData.library.list({ space: props.embed?.space || store.space, area: p.area, goal: p.reference ? 'none' : p.goal,
    include_archived: p.archived ? 1 : 0, collection: collectionOf(), filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.notes, total: res.total }
}
defineExpose({ reload: () => list.value?.reload() })
</script>
