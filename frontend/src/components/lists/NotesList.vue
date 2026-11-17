<template>
  <!-- the notes as a list, on the cross-type index: /library?view=list, and the Notes tab of the goal page -->
  <ListView ref="list" :title="embed ? null : 'Notes'" noun="notes" :screen="embed ? embed.screen + (collection === 'Wiki' ? '-wiki' : '-notes') : 'library'" :fixed="embed?.fixed" :active="embed ? embed.active : true" doctype="Life Index" :spec="SPEC" :flag-labels="embed?.fixed?.goal ? { archived: 'Include archived' } : { archived: 'Include archived', reference: 'Reference only' }" :quiet="['archived']"
    :virtual="VIRTUAL" :hidden="HIDDEN" :quick="['title', 'area', 'goal']" :synthetic="SYNTHETIC" :fetch="fetchList" :row-ref="(r) => 'note:' + r.name"
    :empty-title="collection === 'Wiki' ? 'No wiki pages here yet.' : 'No notes yet.'"
    :empty-hint="collection === 'Wiki' ? 'The agent writes wiki pages from the sources you add with Add to wiki.' : 'Notes hold reference material and notes on your goals, in Markdown. Add one with New note.'">
    <template #sub>Notes in {{ store.space }}</template>
    <template #actions><slot name="actions" /></template>
    <template #cell-title="{ row }"><span class="break-words font-medium text-ink-gray-9">{{ row.title }}</span></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="{ query: { ...$route.query, area: row.area, open: undefined } }">{{ row.area_name }}</RouterLink></template>
    <template #cell-goal="{ row }"><span class="truncate">{{ row.goal_title }}</span></template>
    <template #cell-record_date="{ row }"><span class="whitespace-nowrap">{{ short(row.record_date || row.modified, true) }}</span></template>
    <template #cell-kind><span class="truncate">Note</span></template>
    <template #cell-_tags="{ row }"><span class="truncate text-sm text-ink-gray-6">{{ row.tags.map((t) => '#' + t).join(' ') }}</span></template>
    <template #stack="{ row }"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
      <div class="text-sm text-ink-gray-6">{{ [row.area_name, row.goal_title, 'edited ' + short(row.modified, true), ...row.tags.map((t) => '#' + t)].filter(Boolean).join(' · ') }}</div></template>
  </ListView>
</template>
<script setup>
import { ref } from 'vue'
import ListView from '@/components/ListView.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'

// inside a record page's tab (the goal page): { screen, space, fixed: { goal }, active(route) }
// collection: My notes, Wiki (the assistant's notes) or all
const props = defineProps({ embed: { type: Object, default: null }, collection: { type: String, default: 'My notes' } })
const list = ref(null)
// the short URL parameters of the list (lib/filterUrl.js). reference=1 is "Reference only": notes with no goal
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'goal', field: 'goal', kind: 'link' }, { key: 'tag', field: 'tag', kind: 'value' },
  { key: 'reference', kind: 'flag' }, { key: 'archived', kind: 'flag' }]
const VIRTUAL = [{ fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' }, { fieldname: 'goal', label: 'Goal', fieldtype: 'Link', options: 'Life Goal' },
  { fieldname: 'tag', label: 'Tag', fieldtype: 'Link', options: 'Life Tag' }]
const HIDDEN = ['ref_doctype', 'ref_name', 'kind', 'search_text', 'also_in_csv', 'tags_csv', 'status', 'record_owner']
const SYNTHETIC = [{ key: '_tags', label: 'Tags' }]
async function fetchList({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await api('library.list', { space: props.embed?.space || store.space, area: p.area, goal: p.reference ? 'none' : p.goal, tag: p.tag,
    include_archived: p.archived ? 1 : 0, collection: props.collection, filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.notes, total: res.total }
}
defineExpose({ reload: () => list.value?.reload() })
</script>
