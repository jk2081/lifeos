<template>
  <ListView ref="list" title="Archive" noun="archived records" :filters="FILTERS" :columns="COLUMNS" :fetch="fetch" :row-ref="(r) => refOf(r.ref_doctype, r.ref_name)"
    :row-key="(r) => r.ref_doctype + r.ref_name" :group-by="(r) => (route.query.sort ? null : r.area_name || 'Unfiled')" default-sort="by area, newest first"
    empty-title="Nothing is archived."
    empty-hint="Done tasks, finished inbox items and quiet chats move here after the number of days in Settings. Completed projects move here at once with their records."
    @loaded="(res) => (projects = res.projects)">
    <template #sub>Archived records by area. Nothing here is deleted.</template>
    <template #above>
      <section v-if="projects.length">
        <h2 class="sh">Projects</h2>
        <div class="cd list"><div v-for="p in projects" :key="p.name" class="rw rowlink" :class="{ on: current && current.ref === 'project:' + p.name }" style="align-items: center"
          :data-ref="'project:' + p.name" @click="(e) => !e.target.closest('button') && openRef('project:' + p.name)">
          <div class="grow"><div class="ttl">{{ p.title }}</div><div class="mt">{{ [p.area_name, p.status, p.archived_on && 'archived ' + short(p.archived_on, true)].filter(Boolean).join(' · ') }}</div></div>
          <button v-if="canWrite()" class="bt s" type="button" @click="restore('Life Project', p.name)">Restore with its records</button></div></div>
      </section>
    </template>
    <template #cell-title="{ row }"><div class="ttl">{{ row.title || 'Untitled' }}</div><div v-if="row.project_title" class="mt">{{ row.project_title }}</div></template>
    <template #cell-kind="{ row }"><span class="mt">{{ KIND[row.kind] || row.kind }}</span></template>
    <template #cell-archived="{ row }"><span class="mt">{{ [row.archived_on && short(row.archived_on, true), REASON[row.archive_reason]].filter(Boolean).join(', ') }}</span></template>
    <template #cell-restore="{ row }"><button v-if="canWrite()" class="bt s" type="button" @click="restore(row.ref_doctype, row.ref_name)">Restore</button></template>
    <template #stack="{ row }">
      <div style="display: flex; gap: 10px; align-items: center">
        <div style="flex: 1; min-width: 0"><div class="ttl">{{ row.title || 'Untitled' }}</div>
          <div class="mt">{{ [KIND[row.kind] || row.kind, row.project_title, row.archived_on && 'archived ' + short(row.archived_on, true), REASON[row.archive_reason]].filter(Boolean).join(' · ') }}</div></div>
        <button v-if="canWrite()" class="bt s" type="button" @click="restore(row.ref_doctype, row.ref_name)">Restore</button>
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ListView from '@/components/ListView.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { current, openRef, refOf } from '@/lib/pane'

const REASON = { Auto: 'by the daily job', Manual: 'by hand', Project: 'with its project' }
const KIND = { Inbox: 'Inbox item', 'Journal Page': 'Journal page', Document: 'Vault document', Chat: 'AI chat' }
const route = useRoute()
const list = ref(null)
const projects = ref([])
const FILTERS = computed(() => [
  { key: 'type', label: 'Type', all: 'Any type', options: [{ value: 'Life Task', label: 'Tasks' }, { value: 'Life Note', label: 'Notes' }, { value: 'Life Inbox Item', label: 'Inbox items' },
    { value: 'Life Chat Log', label: 'Chats' }, { value: 'Life Vault Document', label: 'Vault documents' }, { value: 'Life Journal Page', label: 'Journal pages' }] },
  { key: 'area', label: 'Area', all: 'All areas', options: [...areaOptions(), { value: 'none', label: 'Unfiled' }] },
  { key: 'reason', label: 'Archived', all: 'Archived any way', quiet: true, options: Object.entries(REASON).map(([value, label]) => ({ value, label })) },
  { key: 'archived_from', label: 'Archived from', type: 'date', quiet: true }, { key: 'archived_to', label: 'Archived to', type: 'date', quiet: true },
])
const COLUMNS = [{ key: 'title', label: 'Record', width: 'minmax(200px, 2fr)', sort: 'title' }, { key: 'kind', label: 'Type', sort: 'kind' },
  { key: 'area_name', label: 'Area', sort: 'area' }, { key: 'archived', label: 'Archived', width: 'minmax(0, 1.4fr)' }, { key: 'restore', label: '', width: 'max-content', align: 'right' }]
async function fetch({ filters: f, sort, dir, start, page_length }) {
  const res = await api('archive.list', { space: store.space, doctype: f.type || undefined, area: f.area || undefined, reason: f.reason || undefined,
    archived_from: f.archived_from || undefined, archived_to: f.archived_to || undefined, sort: sort || undefined, dir: dir || undefined, start, page_length })
  return { rows: res.records, total: res.total, projects: res.projects }
}
async function restore(doctype, name) {
  if (await tryCall(() => api('archive.restore', { doctype, name }), 'Restored.')) list.value.reload()
}
onMounted(loadLookups)
</script>
