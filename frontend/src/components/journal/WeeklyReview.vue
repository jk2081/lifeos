<template>
  <Teleport to="#jr-actions">
    <Button icon="lucide-chevron-left" label="Previous week" @click="step(-7)" />
    <Button icon="lucide-chevron-right" label="Next week" @click="step(7)" />
  </Teleport>
  <div v-if="d" class="page-body">
    <div class="stats">
      <Stat :label="d.cycle ? `Week ${d.cycle.week} score` : '12 Week Year'" :value="d.cycle ? Math.round(d.cycle.percent) + '%' : '—'">
        <template #sub><span class="max-md:hidden">{{ d.cycle ? `${d.cycle.done} of ${d.cycle.planned} ticks · ${d.cycle.title}` : 'No cycle in this week' }}</span></template>
      </Stat>
      <Stat label="Tasks done"><NumLink :to="door('Done')" data-door="review-done">{{ d.done.length }}</NumLink>
        <template #sub><NumLink class="max-md:hidden" :to="door('Carried')" data-door="review-carried"><span>{{ d.carried.length }}</span> carried forward</NumLink></template>
      </Stat>
      <Stat label="Open loops"><NumLink :to="{ path: '/tasks', query: { view: 'loops' } }" data-door="review-loops">{{ d.open_loops_total }}</NumLink>
        <template #sub><span class="max-md:hidden">Older than 14 days, no date</span></template>
      </Stat>
    </div>
    <div class="cols">
      <div class="half">
        <section><SectionHead>Habits this week</SectionHead>
          <Card flush><Row v-for="h in d.habits" :key="h.habit" class="!items-center !gap-3.5">
            <span class="w-[84px] flex-none">{{ h.title }}</span><div class="min-w-0 flex-1"><Progress size="sm" :value="Math.min(100, (100 * h.done) / h.target)" /></div>
            <span class="tabular-nums">{{ h.done }}/{{ h.target }}</span></Row>
            <Empty v-if="!d.habits.length" title="No habits were tracked this week." hint="Habits come from the month plan." /></Card>
        </section>
        <section><SectionHead>Done this week</SectionHead>
          <Card flush><TaskRow v-for="t in d.done" :key="t.name" :task="t" :today="store.today" readonly />
            <Empty v-if="!d.done.length" title="No tasks were completed this week." hint="Tasks you tick off show here." /></Card>
        </section>
        <section v-if="d.carried.length"><SectionHead>Carried forward</SectionHead>
          <Card flush><TaskRow v-for="t in d.carried" :key="t.name" :task="t" :today="store.today" readonly /></Card>
        </section>
        <section><SectionHead :count="d.open_loops_total" :to="{ path: '/tasks', query: { view: 'loops' } }">Open loops</SectionHead>
          <Card flush><TaskRow v-for="t in d.open_loops.slice(0, 8)" :key="t.name" :task="t" :today="store.today" with-due :readonly="!canWrite()" @toggle="done" />
            <Empty v-if="!d.open_loops.length" title="No open loops." hint="Open tasks older than 14 days with no due date gather here." /></Card>
        </section>
      </div>
      <div class="half">
        <section><SectionHead>Decide</SectionHead>
          <Card flush>
            <Row v-for="t in d.decide" :key="t.name" class="flex-wrap !items-center" :pane="'task:' + t.name" :label="t.title">
              <div class="min-w-0 flex-[1_1_200px]"><div class="break-words text-base-medium text-ink-gray-9">{{ t.title }}</div><div class="text-sm text-ink-gray-6">{{ t.area_name || 'Unfiled' }} · not touched since {{ short(t.last_touched_on || t.creation, true) }}</div></div>
              <div v-if="canWrite()" class="chips"><Button class="relative" label="Do this week" @click="decide(t, 'do')" />
                <Button class="relative" label="Carry" @click="decide(t, 'carry')" /><Button class="relative" label="Drop" @click="decide(t, 'drop')" /></div>
            </Row>
            <Empty v-if="!d.decide.length" title="Nothing to decide." :hint="`Open tasks not touched for ${d.stale_days} days are listed here. They are never archived for you.`" />
          </Card>
        </section>
        <section v-if="d.archived.length"><SectionHead :count="d.archived.length" :to="{ path: '/archive', query: { reason: 'Auto', archived_from: d.week_start, archived_to: d.week_end } }" door="review-archived">Archived this week by the daily job</SectionHead>
          <Card flush><Row v-for="a in d.archived" :key="a.name" class="!items-center" :pane="refOf(a.doctype, a.name)" :label="a.title">
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ a.title }}</div><div class="text-sm text-ink-gray-6">{{ a.doctype.replace('Life ', '') }} · archived {{ short(a.archived_on) }}</div></div>
            <Button v-if="canWrite()" class="relative" label="Undo" @click="undo(a)" /></Row></Card>
        </section>
        <section><SectionHead>Latest check-in <template #action><Button variant="ghost" size="sm" label="Check-ins" route="/journal/checkins" /></template></SectionHead>
          <Card flush>
            <template v-if="d.latest_checkin"><Row><span class="text-sm text-ink-gray-6">{{ long(d.latest_checkin.date, true) }}</span></Row>
              <Row v-for="s in d.latest_checkin.scores" :key="s.dimension"><span class="min-w-0 flex-1">{{ s.dimension_name }}</span>
                <span class="text-sm text-ink-gray-6">{{ range(s.habits_low, s.habits_high) }} · {{ range(s.situation_low, s.situation_high) }}</span></Row></template>
            <Empty v-else title="No check-in yet." hint="Score each life dimension under Check-ins." />
          </Card>
        </section>
        <section><SectionHead>Your notes for the week</SectionHead>
          <Textarea v-model="note" :rows="8" aria-label="Your notes for the week" placeholder="What went well, what did not, what changes next week. Markdown." :disabled="!canWrite()" @update:model-value="queue" />
          <div class="mt-2 flex items-center justify-between gap-2">
            <span class="text-sm text-ink-gray-6">{{ state || `Saved as the note “${d.note.title}” under Reviews.` }}
              <a v-if="d.note.name" href="#" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" @click.prevent="openRef('note:' + d.note.name)">Open note</a></span>
            <Button v-if="canWrite()" variant="solid" label="Save notes" @click="saveNote" />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Button, Progress, Textarea } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Stat from '@/components/ui/Stat.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { addDays, long, short, startOfWeek } from '@/lib/dates'
import { onRecordChanged, openRef, refOf } from '@/lib/pane'

const emit = defineEmits(['sub'])
const weekStart = ref(startOfWeek(store.today))
const d = ref(null)
const note = ref('')
const state = ref('')
// the week's numbers lead to the tasks they count: this status, completed inside this week, archived ones included
const door = (status) => ({ path: '/tasks', query: { view: 'table', status, completed_from: d.value.week_start, completed_to: d.value.week_end, archived: '1' } })
let timer = null
const range = (lo, hi) => (lo == null ? '—' : lo === hi ? String(lo) : `${lo}-${hi}`)

async function load() {
  const res = await tryCall(() => api('journal.weekly_review', { space: store.space, week_start: weekStart.value }))
  if (!res) return
  d.value = res
  note.value = res.note.content_md
  state.value = ''
  emit('sub', `Week of ${long(res.week_start)} to ${long(res.week_end, true)}`)
}
function step(n) {
  weekStart.value = addDays(weekStart.value, n)
  load()
}
function queue() {
  state.value = 'Typing…'
  clearTimeout(timer)
  timer = setTimeout(saveNote, 2000)
}
async function saveNote() {
  clearTimeout(timer)
  const res = await tryCall(() => api('journal.save_review_note', { space: store.space, week_start: weekStart.value, content_md: note.value }))
  if (res) {
    d.value.note.name = res.note
    state.value = 'Saved.'
  }
}
async function decide(t, decision) {
  if (await tryCall(() => api('tasks.decide_stale', { task: t.name, decision }), { do: 'Due this week.', carry: 'Carried to next month.', drop: 'Dropped.' }[decision])) load()
}
async function done(t) {
  if (await tryCall(() => api('tasks.set_status', { task: t.name, status: 'Done' }))) load()
}
async function undo(a) {
  if (await tryCall(() => api('archive.restore', { doctype: a.doctype, name: a.name }), 'Restored.')) load()
}
onRecordChanged(load)
onMounted(load)
</script>
