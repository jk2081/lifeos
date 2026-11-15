<template>
  <ListView :title="embed ? null : 'Timeline'" sub="Everything captured, by day, newest first" noun="records" :screen="embed ? embed.screen + '-timeline' : 'timeline'"
    :fixed="embed?.fixed" :active="embed ? embed.active : true" doctype="Life Index" mode="feed" :spec="SPEC"
    :flag-labels="{ archived: 'Include archived' }" :quick="['ref_doctype', 'area', 'title']" :virtual="VIRTUAL" :hidden="HIDDEN" :fetch="fetch" :page-size="60"
    :row-ref="(r) => refOf(r.ref_doctype, r.ref_name)" :row-key="(r) => r.ref_doctype + r.ref_name + r.kind" :row-label="(r) => r.title || 'Untitled'"
    :group-by="(r) => `${weekday(r.record_date)}, ${long(r.record_date, true)}`" empty-title="Nothing on the timeline yet."
    empty-hint="Every inbox item, task, note, document, chat, journal page and check-in shows here on the day it was captured.">
    <template #row="{ row: e }">
      <div class="flex items-start gap-2.5">
        <div class="min-w-0 flex-1">
          <div class="break-words text-base-medium text-ink-gray-9">{{ e.title || 'Untitled' }}</div>
          <div class="flex flex-wrap items-center gap-x-1 text-sm text-ink-gray-6">
            {{ [KIND[e.kind] || e.kind, e.area_name, e.project_title].filter(Boolean).join(' · ') }}
            <template v-if="e.filed_by"> · <Avatar size="xs" :label="e.filed_by" /> by {{ e.filed_by }}</template>
            <template v-if="e.is_archived"> · archived</template>
            <template v-if="e.pending"> · <NumLink class="relative" :to="{ query: { ...route.query, open: refOf(e.ref_doctype, e.ref_name), focus: 'pending' } }">{{ e.pending }} of {{ e.proposals }} proposals pending</NumLink></template>
          </div>
        </div>
        <Badge :theme="THEME[e.kind] || 'gray'" :label="SHORT[e.kind] || e.kind" />
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Avatar, Badge } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import NumLink from '@/components/ui/NumLink.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { long, weekday } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { refOf } from '@/lib/pane'

const TYPES = ['Life Inbox Item', 'Life Task', 'Life Note', 'Life Vault Document', 'Life Chat Log', 'Life Journal Page', 'Life Check-in', 'Life Month Plan']
const KIND = { Inbox: 'Added to the Inbox', Task: 'Task created', 'Task Done': 'Task completed', Note: 'Note', Document: 'Vault document',
  Chat: 'AI chat', 'Journal Page': 'Journal page', 'Check-in': 'Check-in', 'Month Plan': 'Month plan' }
const SHORT = { 'Task Done': 'Done', 'Journal Page': 'Page', 'Month Plan': 'Month', Document: 'Doc' }
const THEME = { Task: 'blue', 'Task Done': 'green', Inbox: 'amber' }
// a cross-type list: the filters are columns of Life Index. The area filter is this one area (sub-areas have their own pages).
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'doctype', field: 'ref_doctype', kind: 'value' },
  { key: 'from', field: 'record_date', kind: 'from' }, { key: 'to', field: 'record_date', kind: 'to' }, { key: 'archived', kind: 'flag' }]
const VIRTUAL = [{ fieldname: 'ref_doctype', label: 'Type', fieldtype: 'Select', options: TYPES.join('\n') },
  { fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' }, { fieldname: 'project', label: 'Project', fieldtype: 'Link', options: 'Life Project' }]
const HIDDEN = ['ref_name', 'search_text', 'also_in_csv', 'tags_csv', 'is_archived', 'record_owner']
// inside a record page's tab (the area page): { screen, space, fixed: { area }, active(route) }
const props = defineProps({ embed: { type: Object, default: null } })
const route = useRoute()
async function fetch({ params: p, filters, summary, start, page_length }) {
  const res = await api('timeline.get', { space: props.embed?.space || store.space, area: p.area, doctype: p.doctype, from_date: p.from, to_date: p.to, include_archived: p.archived ? 1 : 0,
    filters, summary, start, page_length })
  return summary ? res : { rows: res.days.flatMap((d) => d.entries), total: res.total }
}
onMounted(loadLookups)
</script>
