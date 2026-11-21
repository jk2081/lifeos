<template>
  <ListView ref="list" title="Someday" noun="items" screen="someday" doctype="Life Task" :spec="SPEC" :tabs="TABS" :quick="['area', 'someday_on']"
    :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => r.ref" :groupable="false"
    :empty-title="EMPTY[tab] || 'Nothing is parked.'" empty-hint="Park a task, goal or note from its pane or from Reset, or add something with New. Each comes back for review after a while.">
    <template #sub><span data-someday-sub>{{ store.space }} · parked, not forgotten · each item comes back for review {{ months }} months after it was parked</span></template>
    <template #actions><Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New" data-new-someday @click="store.newKind = 'someday'" /></template>
    <template #bar><span class="text-sm text-ink-gray-6 max-sm:hidden">Sorted by review date, oldest first</span></template>
    <template #cell-title="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title }}</div>
      <div v-if="row.area_path" class="truncate text-sm text-ink-gray-6">{{ row.area_path }}</div></div></template>
    <template #cell-_type="{ row }"><Badge :theme="THEME[row.type]" :label="typeLabel(row)" data-someday-type /></template>
    <template #cell-_created="{ row }"><span class="tabular-nums">{{ short(row.creation) }}</span></template>
    <template #cell-_parked="{ row }"><span class="tabular-nums">{{ short(row.someday_on) }}</span></template>
    <template #cell-_review="{ row }"><Badge :theme="row.due ? 'red' : 'gray'" :label="reviewLabel(row)" data-someday-review /></template>
    <template #cell-_actions="{ row }"><RowActions :row="row" /></template>
    <template #stack="{ row }">
      <div class="flex flex-col gap-1.5" data-someday-row>
        <div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
        <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"><Badge :theme="THEME[row.type]" :label="typeLabel(row)" /><span v-if="row.area_path">{{ row.area_path }}</span></div>
        <div class="text-sm text-ink-gray-6">Created {{ short(row.creation) }} · parked {{ short(row.someday_on) }} · <span :class="row.due ? 'text-ink-red-8' : ''">{{ reviewLabel(row) }}</span></div>
        <RowActions :row="row" />
      </div>
    </template>
    <template #below>
      <Card class="mt-4 bg-surface-gray-1" data-someday-how>
        <div class="text-base-medium text-ink-gray-9">How Someday works</div>
        <p class="mt-1 text-base text-ink-gray-7">Anything can be parked here: a task, a goal (a long-term goal takes its tasks), or a note for a thought with no action. It leaves Today,
          Tasks and the Open counts, keeps its original creation date, and records the day it was parked. {{ months }} months later it comes up in Reset for a decision:
          <b>Bring back</b> (pick a date, status or cycle), <b>Keep</b> for {{ months }} more months, or <b>Purge</b> (to the trash, 30 days to undo).</p>
      </Card>
    </template>
  </ListView>
  <NewRecord v-if="bringBack.open" v-model="bringBack.open" :title="`Bring back ${bringBack.row?.title || ''}`" action="Bring back" :fields="bringBack.fields"
    :initial="bringBack.initial" :save="doBringBack" @saved="list?.reload()" />
</template>
<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { Badge, Button, Dropdown } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import NewRecord from '@/components/NewRecord.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { onRecordChanged } from '@/lib/pane'
import { askBringBack, bringBack, doBringBack, keep, purge } from '@/lib/someday'
import { askScope } from '@/lib/ask'

// state tabs on tab=: All (default), Due for review, and one per kind
const TABS = { key: 'tab', field: 'status', label: 'Someday kind', items: [{ value: 'all', label: 'All' }, { value: 'due', label: 'Due for review' },
  { value: 'tasks', label: 'Tasks' }, { value: 'goals', label: 'Goals' }, { value: 'notes', label: 'Notes' }] }
const EMPTY = { due: 'Nothing is due for review.', tasks: 'No parked tasks.', goals: 'No parked goals.', notes: 'No parked notes.' }
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'tab', field: 'status', kind: 'value' },
  { key: 'parked_from', field: 'someday_on', kind: 'from' }, { key: 'parked_to', field: 'someday_on', kind: 'to' }]
const SYNTHETIC = [{ key: '_type', label: 'Type', width: '10rem', place: 'end' }, { key: '_created', label: 'Created', width: '6rem', place: 'end' },
  { key: '_parked', label: 'Parked', width: '6rem', place: 'end' }, { key: '_review', label: 'Review', width: '8rem', place: 'end' },
  { key: '_actions', label: '', width: '12rem', align: 'right', place: 'end' }]
const HIDDEN = ['status', 'goal', 'someday_note']
const THEME = { Note: 'violet', Goal: 'green', Task: 'gray' }
const list = ref(null)
const months = ref(3)
const tab = computed(() => list.value?.tab || 'all')
const typeLabel = (r) => (r.type === 'Goal' && r.tasks ? `Goal · ${r.tasks} task${r.tasks === 1 ? '' : 's'}`: r.type)
function reviewLabel(r) {
  if (r.due) return 'Review due'
  if (!r.someday_review_on) return ''
  const days = Math.round((new Date(r.someday_review_on) - new Date(store.today)) / 86400e3)
  return days > 45 ? `In ${Math.round(days / 30)} months` : `In ${days} day${days === 1 ? '' : 's'}`
}
const RowActions = (p) => {
  const r = p.row
  if (!canWrite()) return null
  return h('div', { class: 'relative flex items-center justify-end gap-1', 'data-someday-actions': '' }, [
    h(Button, { label: 'Bring back', 'data-bring-back': '', onClick: () => askBringBack(r) }),
    h(Button, { variant: 'ghost', label: 'Purge', 'data-purge': '', onClick: async () => { if (await purge(r)) list.value?.reload() } }),
    h(Dropdown, { options: [{ label: `Keep for ${months.value} more months`, icon: 'lucide-clock', onClick: async () => { await keep(r); list.value?.reload() } }] },
      () => h(Button, { variant: 'ghost', icon: 'lucide-ellipsis', label: 'More for ' + r.title })),
  ])
}
RowActions.props = ['row']

async function fetch({ params: p, tab: t, filters, order_by, start, page_length }) {
  const res = await api('someday.list', { space: store.space, tab: t, area: p.area, filters, order_by, start, page_length })
  months.value = res.review_months || 3
  return { rows: res.rows, total: res.total, tabs: res.tabs }
}
onRecordChanged(() => list.value?.reload())
onMounted(() => {})
// Ask from Someday: the items on screen
askScope(() => ({ kind: 'items', label: 'Items on Someday', items: (list.value?.rows || []).map((r) => ({ doctype: r.doctype, name: r.name })) }))
</script>
