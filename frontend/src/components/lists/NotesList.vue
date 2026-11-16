<template>
  <!-- the notes as a list, on the cross-type index: /library?view=list, and the Notes tab of the area and project pages -->
  <ListView ref="list" :title="embed ? null : 'Notes'" noun="notes" :screen="embed ? embed.screen + (collection === 'Wiki' ? '-wiki' : '-notes') : 'library'" :fixed="embed?.fixed" :active="embed ? embed.active : true" doctype="Life Index" :spec="SPEC" :flag-labels="embed?.fixed?.project ? { archived: 'Include archived' } : { archived: 'Include archived', reference: 'Reference only' }" :quiet="['archived']"
    :virtual="VIRTUAL" :hidden="HIDDEN" :quick="['title', 'area', 'project']" :synthetic="SYNTHETIC" :fetch="fetchList" :row-ref="(r) => 'note:' + r.name"
    :empty-title="collection === 'Wiki' ? 'No wiki pages here yet.' : 'No notes yet.'"
    :empty-hint="collection === 'Wiki' ? 'The agent writes wiki pages from the sources you add with Add to wiki.' : 'Notes hold reference material and project notes, in Markdown. Add one with New note.'">
    <template #sub>Notes in {{ store.space }}</template>
    <template #actions><slot name="actions" /></template>
    <template #cell-title="{ row }"><span class="break-words font-medium text-ink-gray-9">{{ row.title }}</span></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-project="{ row }"><span class="truncate">{{ row.project_title }}</span></template>
    <template #cell-record_date="{ row }"><span class="whitespace-nowrap">{{ short(row.record_date || row.modified, true) }}</span></template>
    <template #cell-kind><span class="truncate">Note</span></template>
    <template #cell-_tags="{ row }"><span class="truncate text-sm text-ink-gray-6">{{ row.tags.map((t) => '#' + t).join(' ') }}</span></template>
    <template #stack="{ row }"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
      <div class="text-sm text-ink-gray-6">{{ [row.area_name, row.project_title, 'edited ' + short(row.modified, true), ...row.tags.map((t) => '#' + t)].filter(Boolean).join(' · ') }}</div></template>
  </ListView>
</template>
<script setup>
import { ref } from 'vue'
import ListView from '@/components/ListView.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'

// inside a record page's tab (the area or project page): { screen, space, fixed: { area } or { project }, active(route) }
// collection: My notes (the Notes screen and the area page's Notes tab) or Wiki (the area page's Wiki tab)
const props = defineProps({ embed: { type: Object, default: null }, collection: { type: String, default: 'My notes' } })
const list = ref(null)
// the short URL parameters of the list (lib/filterUrl.js). reference=1 is "Reference only": notes with no project
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'project', field: 'project', kind: 'link' }, { key: 'tag', field: 'tag', kind: 'value' },
  { key: 'reference', kind: 'flag' }, { key: 'archived', kind: 'flag' }]
const VIRTUAL = [{ fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' }, { fieldname: 'project', label: 'Project', fieldtype: 'Link', options: 'Life Project' },
  { fieldname: 'tag', label: 'Tag', fieldtype: 'Link', options: 'Life Tag' }]
const HIDDEN = ['ref_doctype', 'ref_name', 'kind', 'search_text', 'also_in_csv', 'tags_csv', 'status', 'record_owner']
const SYNTHETIC = [{ key: '_tags', label: 'Tags' }]
async function fetchList({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await api('library.list', { space: props.embed?.space || store.space, area: p.area, project: p.reference ? 'none' : p.project, tag: p.tag,
    include_archived: p.archived ? 1 : 0, collection: props.collection, filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.notes, total: res.total }
}
defineExpose({ reload: () => list.value?.reload() })
</script>
