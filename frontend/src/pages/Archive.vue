<template>
  <ListView ref="list" title="Archive" noun="archived records" screen="archive" doctype="Life Index" :spec="SPEC" :tabs="TABS" :quick="['area', 'title']" :virtual="VIRTUAL"
    :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => refOf(r.ref_doctype, r.ref_name)" :row-key="(r) => r.ref_doctype + r.ref_name"
    :row-label="(r) => r.title || 'Untitled'" :group-by="(r) => (route.query.sort ? '' : r.area_name || 'Unfiled')" empty-title="Nothing is archived."
    empty-hint="Done tasks, finished inbox items and quiet chats move here after the number of days in Settings. Completed projects move here at once with their records."
    @loaded="(res) => (projects = res.projects)">
    <template #sub>Archived records by area. Nothing here is deleted.</template>
    <template #above>
      <section v-if="projects.length" data-archived-projects>
        <SectionHead>Projects</SectionHead>
        <Card flush>
          <Row v-for="p in projects" :key="p.name" class="!items-center" :pane="'project:' + p.name" :label="p.title">
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ p.title }}</div>
              <div class="text-sm text-ink-gray-6">{{ [p.area_name, p.status, p.archived_on && 'archived ' + short(p.archived_on, true)].filter(Boolean).join(' · ') }}</div></div>
            <Button v-if="canWrite()" class="relative" label="Restore with its records" @click="restore('Life Project', p.name)" />
          </Row>
        </Card>
      </section>
    </template>
    <template #cell-title="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title || 'Untitled' }}</div></div></template>
    <template #cell-kind="{ row }"><span class="truncate text-ink-gray-6">{{ KIND[row.kind] || row.kind }}</span></template>
    <template #cell-area="{ row }"><span class="truncate">{{ row.area_name }}</span></template>
    <template #cell-project="{ row }"><span class="truncate">{{ row.project_title }}</span></template>
    <template #cell-_archived="{ row }"><span class="truncate text-sm text-ink-gray-6">{{ [row.archived_on && short(row.archived_on, true), REASON[row.archive_reason]].filter(Boolean).join(', ') }}</span></template>
    <template #cell-_restore="{ row }"><Button v-if="canWrite()" class="relative" size="sm" label="Restore" @click="restore(row.ref_doctype, row.ref_name)" /></template>
    <template #stack="{ row }">
      <div class="flex items-center gap-2.5">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title || 'Untitled' }}</div>
          <div class="text-sm text-ink-gray-6">{{ [KIND[row.kind] || row.kind, row.project_title, row.archived_on && 'archived ' + short(row.archived_on, true), REASON[row.archive_reason]].filter(Boolean).join(' · ') }}</div></div>
        <Button v-if="canWrite()" class="relative" size="sm" label="Restore" @click="restore(row.ref_doctype, row.ref_name)" />
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { useLinkScope } from '@/framework/linkScope'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { refOf } from '@/lib/pane'

const REASON = { Auto: 'by the daily job', Manual: 'by hand', Project: 'with its project' }
const KIND = { Inbox: 'Inbox item', 'Journal Page': 'Journal page', Document: 'Vault document', Chat: 'AI chat' }
const TYPES = ['Life Task', 'Life Note', 'Life Inbox Item', 'Life Chat Log', 'Life Vault Document', 'Life Journal Page']
// the archive is a cross-type list: its filters are columns of Life Index, plus two the server reads from the records themselves
// the Archive is the one screen whose area filter offers archived areas, marked "(archived)"
useLinkScope({ archived: true })
const SPEC = [{ key: 'type', field: 'ref_doctype', kind: 'value', label: 'Type' }, { key: 'area', field: 'area', kind: 'link' }, { key: 'reason', field: 'archive_reason', kind: 'value' },
  { key: 'archived_from', field: 'archived_on', kind: 'from' }, { key: 'archived_to', field: 'archived_on', kind: 'to' }]
const VIRTUAL = [
  { fieldname: 'ref_doctype', label: 'Type', fieldtype: 'Select', options: TYPES.join('\n') },
  { fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' },
  { fieldname: 'project', label: 'Project', fieldtype: 'Link', options: 'Life Project' },
  { fieldname: 'archive_reason', label: 'Archived', fieldtype: 'Select', options: Object.keys(REASON).join('\n') },
  { fieldname: 'archived_on', label: 'Archived on', fieldtype: 'Date' },
]
// the state tabs: one per record type, on type=. All is the default
const TABS = { key: 'type', field: 'ref_doctype', label: 'Record type', items: [{ value: 'all', label: 'All' }, { value: 'Life Task', label: 'Tasks' }, { value: 'Life Note', label: 'Notes' },
  { value: 'Life Chat Log', label: 'Chats' }, { value: 'Life Vault Document', label: 'Documents' }, { value: 'Life Inbox Item', label: 'Inbox items' }, { value: 'Life Journal Page', label: 'Journal pages' }] }
const HIDDEN = ['ref_name', 'search_text', 'also_in_csv', 'tags_csv', 'is_archived', 'record_owner', 'status']
const SYNTHETIC = [{ key: '_archived', label: 'Archived', width: 'minmax(0, 1.4fr)', place: 'end' }, { key: '_restore', label: '', width: '6rem', align: 'right', place: 'end' }]
const route = useRoute()
const list = ref(null)
const projects = ref([])
async function fetch({ params: p, tab, filters, order_by, summary, start, page_length }) {
  const res = await api('archive.list', { space: store.space, doctype: tab === 'all' ? undefined : tab, area: p.area, reason: p.reason, archived_from: p.archived_from, archived_to: p.archived_to,
    filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.records, total: res.total, projects: res.projects, tabs: res.tabs }
}
async function restore(doctype, name) {
  if (await tryCall(() => api('archive.restore', { doctype, name }), 'Restored.')) list.value.reload()
}
onMounted(loadLookups)
</script>
