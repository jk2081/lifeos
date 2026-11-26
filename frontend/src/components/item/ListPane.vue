<template>
  <div class="flex flex-col gap-3" data-list-pane :data-list="kind">
    <template v-if="loaded">
      <Card v-if="data.rules" flush class="!px-4">
        <RuleList :rules="data.rules" :writable="canWrite()" empty="No rules learned in this period." @changed="load" />
      </Card>
      <Card v-else-if="data.habits" flush class="!px-4">
        <Row v-for="h in data.habits" :key="h.habit" :label="h.title" class="!items-center" data-list-row>
          <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ h.title }}</span>
          <Button size="sm" :variant="h.done ? 'solid' : 'outline'" :disabled="!canWrite()" :label="h.done ? 'Done' : 'Tick'" :aria-pressed="h.done" :aria-label="`${h.title}, ${h.done ? 'done' : 'not done'}`"
            data-list-habit class="relative" @click="tick(h)" />
        </Row>
        <Empty v-if="!data.habits.length" title="No habits yet." hint="A habit you track shows here, ticked each day." />
      </Card>
      <div v-else-if="data.grouped && data.rows.length" class="flex flex-col gap-4" data-waiting-list :data-by="byPerson ? 'person' : 'group'">
        <section v-for="g in sections" :key="g.key" :data-waiting-group="g.key">
          <SectionHead :count="g.rows.length">{{ g.label }}
            <template v-if="g.key === 'later'" #action><Button size="sm" variant="ghost" :label="laterOpen ? 'Fold' : 'Show'" data-waiting-later-toggle :aria-expanded="laterOpen" @click="laterOpen = !laterOpen" /></template>
          </SectionHead>
          <Card v-if="g.key !== 'later' || byPerson || laterOpen" flush class="!px-4">
            <WaitingRow v-for="r in g.rows" :key="r.task" :r="r" :active="data.rows.indexOf(r) === active" @open="remember" @changed="load" />
          </Card>
        </section>
      </div>
      <Card v-else flush class="!px-4">
        <template v-for="(r, i) in data.rows" :key="r.ref + i">
          <WaitingRow v-if="r.task" :r="r" :active="i === active" @open="remember" @changed="load" />
          <Row v-else :pane="r.ref" :label="r.title" class="!items-center" :class="i === active && '!bg-surface-gray-2'" data-list-row :data-active="i === active || undefined"
            :data-ref="r.ref" @click.capture="remember(r)">
            <div class="min-w-0 flex-1">
              <div class="break-words text-base text-ink-gray-9">{{ r.title }}</div>
              <div v-if="r.sub" class="text-sm" :class="r.tone === 'warn' ? 'text-ink-amber-9' : 'text-ink-gray-6'">{{ r.sub }}</div>
            </div>
            <span v-if="r.percent != null" class="shrink-0 text-sm tabular-nums text-ink-gray-6">{{ Math.round(r.percent) }}%</span>
          </Row>
        </template>
        <Empty v-if="!data.rows.length && kind.startsWith('waiting')" title="Nobody owes you anything." hint="Hand something off and it shows here, with the day to look again." data-list-empty />
        <Empty v-else-if="!data.rows.length" title="Nothing here." hint="What this number counts is empty for this period." data-list-empty />
      </Card>
      <div v-if="kind === 'waiting' && canWrite()" class="flex flex-wrap items-center gap-2" data-waiting-foot>
        <Button variant="solid" icon-left="lucide-plus" label="Hand off" data-waiting-handoff @click="handOpen = true" />
        <Button v-if="data.rows.length" :label="byPerson ? 'By status' : 'By person'" icon-left="lucide-users" data-waiting-by-person :aria-pressed="byPerson" @click="byPerson = !byPerson" />
      </div>
      <HandOffDialog v-if="kind === 'waiting'" v-model="handOpen" :space="store.space" @done="load" />
    </template>
    <div v-else class="flex flex-col gap-2"><Skeleton class="h-12 w-full" /><Skeleton class="h-12 w-full" /></div>
  </div>
</template>
<script setup>
// A number's list in the pane (issue 123): `?open=list:needs-you`, `list:waiting`, `list:waiting-overdue`, `list:rules`, `list:filed-alone`, `list:done` and the rest of
// dashboard.LIST_KINDS. The period is the Today view's (the path) around its `date=`. A row opens its record in this same pane with Back to the list (`back=`);
// j and k move through the rows, Enter opens the one marked. Built once here so Brain and Goals can show a list in the pane too.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import Empty from '@/components/Empty.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import WaitingRow from '@/components/item/WaitingRow.vue'
import HandOffDialog from '@/components/item/HandOffDialog.vue'
import RuleList from '@/components/brain/RuleList.vue'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { canWrite, store } from '@/lib/store'
import { listRows, onRecordChanged, openRef, paneNav } from '@/lib/pane'
import { viewOfPath } from '@/lib/nav'

const props = defineProps({ name: String, type: String })
const rowOf = listRows
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const route = useRoute()
const data = ref({ rows: [] })
const loaded = ref(false)
const active = ref(rowOf[props.name] ?? -1) // the row opened last, kept while a record is on top of this list
const kind = computed(() => props.name.split(':')[0])
// the Waiting list (issue 130): Looks done, Late, This week and Later (folded); By person regroups it by who owes you
const LABELS = { looks_done: 'Looks done', late: 'Late', week: 'This week', later: 'Later' }
const byPerson = ref(false)
const laterOpen = ref(false)
const handOpen = ref(false)
const sections = computed(() => {
  const rows = data.value.rows || []
  if (byPerson.value) {
    const by = {}
    for (const r of rows) (by[r.who || 'Someone'] ||= []).push(r)
    return Object.keys(by).sort().map((who) => ({ key: who, label: who, rows: by[who] }))
  }
  return (data.value.group_order || []).map((k) => ({ key: k, label: LABELS[k], rows: rows.filter((r) => r.group === k) })).filter((g) => g.rows.length)
})
// where each list is whole: its own full page, when it has one
const FULL = { 'needs-you': '/brain', waiting: { path: '/today/week', query: { view: 'review', tab: 'tasks' } }, 'waiting-overdue': { path: '/today/week', query: { view: 'review', tab: 'tasks' } },
  'filed-alone': '/brain/activity', 'came-in': '/brain/activity', rules: { path: '/settings', query: { tab: 'brain' } } }
let seq = 0
async function load() {
  const mine = ++seq
  const res = await tryCall(() => itemData.dashboard.list({ kind: props.name, view: viewOfPath(route.path), date: route.query.date || undefined, space: store.space }))
  if (mine !== seq) return
  if (!res) return emit('missing')
  data.value = res
  loaded.value = true
  paneNav.rows = (res.rows || []).map((r) => r.ref).filter((r) => /^[a-z]+:/.test(r))  // j and k in a record opened from this list step through its rows
  emit('meta', { title: res.title, kind: 'List', fullPage: FULL[kind.value] || undefined })
}
// the row opened last, so Back finds it marked again
const remember = (r) => { active.value = rowOf[props.name] = data.value.rows.findIndex((x) => x.ref === r.ref) }
function tick(h) {
  const on = !h.done
  h.done = on
  tryCall(() => itemData.goals.toggle_habit({ habit: h.habit, date: data.value.date, done: on ? 1 : 0 })).then((ok) => { if (!ok) h.done = !on; else emit('changed') })
}
function onKey(e) {
  if (e.metaKey || e.ctrlKey || e.altKey || !data.value.rows?.length) return
  const t = e.target
  if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || (t.closest && t.closest('[role="listbox"], [role="menu"], [role="combobox"], [role="tablist"]'))) return
  const rows = data.value.rows
  if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); active.value = Math.min(active.value + 1, rows.length - 1) }
  else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); active.value = Math.max(active.value - 1, 0) }
  else if (e.key === 'Enter' && rows[active.value] && !t.closest('button, a')) { e.preventDefault(); openRef(rows[active.value].ref) }
}
onRecordChanged(load)
watch(() => props.name, () => { loaded.value = false; active.value = rowOf[props.name] ?? -1; load() })
onMounted(() => { load(); window.addEventListener('keydown', onKey) })
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  if (!route.query.under) paneNav.rows = []
})
</script>
