<template>
  <Teleport to="#jr-actions">
    <button class="bt s ic" type="button" aria-label="Previous week" @click="step(-7)"><Ico d="m15 6-6 6 6 6" stroke="2" /></button>
    <button class="bt s ic" type="button" aria-label="Next week" @click="step(7)"><Ico d="m9 6 6 6-6 6" stroke="2" /></button>
  </Teleport>
  <div v-if="d" class="bd">
    <div class="stats">
      <div class="cd st"><span class="mt">{{ d.cycle ? `Week ${d.cycle.week} score` : '12 Week Year' }}</span><b>{{ d.cycle ? Math.round(d.cycle.percent) + '%' : '—' }}</b>
        <span class="mt only-desktop">{{ d.cycle ? `${d.cycle.done} of ${d.cycle.planned} ticks · ${d.cycle.title}` : 'No cycle in this week' }}</span></div>
      <div class="cd st"><span class="mt">Tasks done</span><b>{{ d.done.length }}</b><span class="mt only-desktop">{{ d.carried.length }} carried forward</span></div>
      <div class="cd st"><span class="mt">Open loops</span><b>{{ d.open_loops_total }}</b><span class="mt only-desktop">Older than 14 days, no date</span></div>
    </div>
    <div class="cols">
      <div class="half">
        <section><h2 class="sh">Habits this week</h2>
          <div class="cd list"><div v-for="h in d.habits" :key="h.habit" class="rw" style="align-items: center; gap: 14px">
            <span style="width: 84px; flex: none">{{ h.title }}</span><div class="br"><i :style="`width: ${Math.min(100, (100 * h.done) / h.target)}%`"></i></div>
            <span style="font-variant-numeric: tabular-nums">{{ h.done }}/{{ h.target }}</span></div>
            <Empty v-if="!d.habits.length" title="No habits were tracked this week." hint="Habits come from the month plan." /></div>
        </section>
        <section><h2 class="sh">Done this week</h2>
          <div class="cd list"><TaskRow v-for="t in d.done" :key="t.name" :task="t" :today="store.today" readonly @open="openTask = t.name" />
            <Empty v-if="!d.done.length" title="No tasks were completed this week." hint="Tasks you tick off show here." /></div>
        </section>
        <section v-if="d.carried.length"><h2 class="sh">Carried forward</h2>
          <div class="cd list"><TaskRow v-for="t in d.carried" :key="t.name" :task="t" :today="store.today" readonly @open="openTask = t.name" /></div>
        </section>
        <section><h2 class="sh">Open loops <RouterLink class="more" to="/tasks?view=loops">All {{ d.open_loops_total }}</RouterLink></h2>
          <div class="cd list"><TaskRow v-for="t in d.open_loops.slice(0, 8)" :key="t.name" :task="t" :today="store.today" with-due :readonly="!canWrite()" @toggle="done" @open="openTask = t.name" />
            <Empty v-if="!d.open_loops.length" title="No open loops." hint="Open tasks older than 14 days with no due date gather here." /></div>
        </section>
      </div>
      <div class="half">
        <section><h2 class="sh">Decide</h2>
          <div class="cd list">
            <div v-for="t in d.decide" :key="t.name" class="rw" style="flex-wrap: wrap; align-items: center">
              <div class="grow" style="flex-basis: 200px"><div class="ttl">{{ t.title }}</div><div class="mt">{{ t.area_name || 'Unfiled' }} · not touched since {{ short(t.last_touched_on || t.creation, true) }}</div></div>
              <div v-if="canWrite()" class="chips"><button class="bt s" type="button" @click="decide(t, 'do')">Do this week</button>
                <button class="bt s" type="button" @click="decide(t, 'carry')">Carry</button><button class="bt s" type="button" @click="decide(t, 'drop')">Drop</button></div>
            </div>
            <Empty v-if="!d.decide.length" title="Nothing to decide." :hint="`Open tasks not touched for ${d.stale_days} days are listed here. They are never archived for you.`" />
          </div>
        </section>
        <section v-if="d.archived.length"><h2 class="sh">Archived this week by the daily job</h2>
          <div class="cd list"><div v-for="a in d.archived" :key="a.name" class="rw" style="align-items: center">
            <div class="grow"><div class="ttl">{{ a.title }}</div><div class="mt">{{ a.doctype.replace('Life ', '') }} · archived {{ short(a.archived_on) }}</div></div>
            <button v-if="canWrite()" class="bt s" type="button" @click="undo(a)">Undo</button></div></div>
        </section>
        <section><h2 class="sh">Latest check-in <RouterLink class="more" to="/journal/checkins">Check-ins</RouterLink></h2>
          <div class="cd list">
            <template v-if="d.latest_checkin"><div class="rw"><span class="mt">{{ long(d.latest_checkin.date, true) }}</span></div>
              <div v-for="s in d.latest_checkin.scores" :key="s.dimension" class="rw"><span class="grow">{{ s.dimension_name }}</span>
                <span class="mt">{{ range(s.habits_low, s.habits_high) }} · {{ range(s.situation_low, s.situation_high) }}</span></div></template>
            <Empty v-else title="No check-in yet." hint="Score each life dimension under Check-ins." />
          </div>
        </section>
        <section><h2 class="sh">Your notes for the week</h2>
          <textarea v-model="note" class="inp" rows="8" style="width: 100%" placeholder="What went well, what did not, what changes next week. Markdown." :disabled="!canWrite()" @input="queue"></textarea>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; gap: 8px">
            <span class="mt">{{ state || `Saved as the note “${d.note.title}” under Reviews.` }}
              <RouterLink v-if="d.note.name" :to="`/library/${d.note.name}`">Open note</RouterLink></span>
            <button v-if="canWrite()" class="bt p" type="button" @click="saveNote">Save notes</button>
          </div>
        </section>
      </div>
    </div>
  </div>
  <TaskPanel v-if="openTask" :name="openTask" @close="openTask = null" @changed="load" />
</template>
<script setup>
import { onMounted, ref } from 'vue'
import Ico from '@/components/Ico.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import TaskPanel from '@/components/TaskPanel.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { addDays, long, short, startOfWeek } from '@/lib/dates'

const emit = defineEmits(['sub'])
const weekStart = ref(startOfWeek(store.today))
const d = ref(null)
const note = ref('')
const state = ref('')
const openTask = ref(null)
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
onMounted(load)
</script>
