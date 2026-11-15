<template>
  <Teleport to="#jr-actions">
    <button class="bt s ic" type="button" aria-label="Previous month" @click="step(-1)"><Ico d="m15 6-6 6 6 6" stroke="2" /></button>
    <button class="bt s ic" type="button" aria-label="Next month" @click="step(1)"><Ico d="m9 6 6 6-6 6" stroke="2" /></button>
  </Teleport>
  <div v-if="d" class="bd">
    <div v-if="!d.plan" class="cd">
      <Empty :title="`No plan for ${MONTHS[month - 1]} ${year} yet.`" hint="A new plan starts with last month's habits. Goals and the mindsweep start empty." />
      <button v-if="canWrite()" class="bt p" type="button" @click="load(true)">Start this month's plan</button>
    </div>
    <div v-else class="cols3">
      <section>
        <h2 class="sh">Goals <span class="mt" style="font-weight: 400">{{ doneCount }} of {{ d.plan.goals.length }} done</span></h2>
        <div class="cd list">
          <div v-for="g in d.plan.goals" :key="g.row" class="rw" style="align-items: center">
            <input class="ck" type="checkbox" style="margin: 0" :checked="g.status === 'Done'" :disabled="!canWrite() || g.status === 'Carried'" :aria-label="'Done: ' + g.title"
              @change="setGoal(g, { status: g.status === 'Done' ? 'Open' : 'Done' })" />
            <span class="pl n" style="min-width: 26px; justify-content: center">{{ g.priority || '·' }}</span>
            <div class="grow">
              <div class="ttl" :style="g.status === 'Done' || g.status === 'Dropped' ? 'text-decoration: line-through; color: var(--ink-gray-6)' : g.status === 'Carried' ? 'color: var(--ink-gray-6)' : ''">
                {{ g.title }}<span v-if="g.status === 'Carried'" title="Carried to next month"> →</span></div>
              <div class="mt">{{ [g.area_name, g.carried_from ? 'carried from last month' : '', g.status === 'Carried' ? 'carried forward' : '', g.status === 'Dropped' ? 'dropped' : ''].filter(Boolean).join(' · ') }}
                <a v-if="g.task" href="#" @click.prevent="openRef('task:' + g.task)">{{ g.area_name || g.carried_from ? '· ' : '' }}task</a></div>
            </div>
            <Dropdown v-if="canWrite()" :options="goalMenu(g)"><button class="bt t ic" type="button" :aria-label="'Actions for ' + g.title">⋯</button></Dropdown>
          </div>
          <Empty v-if="!d.plan.goals.length" title="No goals this month." hint="Add what you want done this month, with a priority from I to IV." />
          <div v-if="canWrite()" class="rw">
            <select v-model="newPriority" class="inp" style="width: 64px" aria-label="Priority"><option value="">–</option><option v-for="p in ['I', 'II', 'III', 'IV']" :key="p">{{ p }}</option></select>
            <input v-model="newGoal" class="inp" style="flex: 1" placeholder="Add a goal for the month" aria-label="New goal" @keydown.enter="addGoal" />
          </div>
        </div>
      </section>
      <section>
        <h2 class="sh">Mindsweep <a v-if="canWrite()" href="#" class="more" @click.prevent="toggleSweep">{{ editing ? 'Done' : 'Edit' }}</a></h2>
        <div class="cd">
          <textarea v-if="editing" v-model="sweep" class="inp" rows="16" style="width: 100%" placeholder="Everything on your mind. Use ## for a topic and ★ to star one." @input="queueSave"></textarea>
          <Md v-else-if="d.plan.mindsweep_md" :text="d.plan.mindsweep_md" />
          <Empty v-else title="The mindsweep is empty." hint="A free page for everything on your mind this month. Use ## for a topic and ★ to star one." />
        </div>
        <p v-if="editing" class="mt" style="margin: 8px 0 0">{{ saveState }}</p>
      </section>
      <section>
        <h2 class="sh">Habits <RouterLink class="more" to="/journal/habits">Open</RouterLink></h2>
        <div class="cd list">
          <div v-for="h in d.habits.habits" :key="h.habit" class="rw" style="align-items: center">
            <span style="width: 84px; flex: none; overflow: hidden; text-overflow: ellipsis">{{ h.title }}</span>
            <div class="br"><i :style="`width: ${h.percent}%`"></i></div><span style="font-variant-numeric: tabular-nums">{{ h.done }}/{{ h.target }}</span>
          </div>
          <Empty v-if="!d.habits.habits.length" title="No habits this month." hint="Choose the habits to track under Habits, Manage habits." />
        </div>
        <h2 class="sh" style="margin-top: 24px">Latest check-in <RouterLink class="more" to="/journal/checkins">Open</RouterLink></h2>
        <div class="cd list">
          <template v-if="d.latest_checkin">
            <div class="rw"><span class="mt">{{ long(d.latest_checkin.date, true) }}</span></div>
            <div v-for="s in d.latest_checkin.scores" :key="s.dimension" class="rw"><span class="grow">{{ s.dimension_name }}</span>
              <span class="mt" style="white-space: nowrap">{{ range(s.habits_low, s.habits_high) }} · {{ range(s.situation_low, s.situation_high) }}</span></div>
          </template>
          <Empty v-else title="No check-in yet." hint="Score each life dimension under Check-ins." />
        </div>
      </section>
    </div>
  </div>
</template>
<script setup>
import { openRef } from '@/lib/pane'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Dropdown, toast } from 'frappe-ui'
import Ico from '@/components/Ico.vue'
import Md from '@/components/Md.vue'
import Empty from '@/components/Empty.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { MONTHS, long, parse } from '@/lib/dates'

const emit = defineEmits(['sub'])
const router = useRouter()
const now = parse(store.today)
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)
const d = ref(null)
const newGoal = ref('')
const newPriority = ref('')
const editing = ref(false)
const sweep = ref('')
const saveState = ref('')
let timer = null
const doneCount = computed(() => d.value.plan.goals.filter((g) => g.status === 'Done').length)
const range = (lo, hi) => (lo == null ? '—' : lo === hi ? String(lo) : `${lo}-${hi}`)

async function load(create = false) {
  const res = await tryCall(() => api('journal.month', { space: store.space, year: year.value, month: month.value, create: create ? 1 : 0 }))
  if (res) d.value = res
  emit('sub', `${MONTHS[month.value - 1]} ${year.value}`)
}
function step(n) {
  const m = month.value + n
  if (m < 1) { month.value = 12; year.value-- } else if (m > 12) { month.value = 1; year.value++ } else month.value = m
  editing.value = false
  load()
}
async function setGoal(g, values) {
  const res = await tryCall(() => api('journal.save_month_goal', { plan: d.value.plan.name, row: g.row, ...values }))
  if (res) d.value.plan = res
}
async function addGoal() {
  const title = newGoal.value.trim()
  if (!title) return
  newGoal.value = ''
  const res = await tryCall(() => api('journal.save_month_goal', { plan: d.value.plan.name, title, priority: newPriority.value }))
  if (res) d.value.plan = res
}
function goalMenu(g) {
  const items = []
  if (g.status === 'Open') {
    items.push({ label: 'Carry to next month →', onClick: async () => {
      const res = await tryCall(() => api('journal.carry_month_goal', { plan: d.value.plan.name, row: g.row }))
      if (res) { toast.success(`Carried into ${MONTHS[res.month - 1]}.`); load() }
    } })
    items.push({ label: g.task ? 'Open task' : 'Make task', onClick: async () => {
      const res = await tryCall(() => api('journal.make_task_from_goal', { plan: d.value.plan.name, row: g.row }))
      if (res) { if (res.existing) openRef('task:' + res.task); else { toast.success('Task created and linked.'); load() } }
    } })
    items.push({ label: 'Drop', onClick: () => setGoal(g, { status: 'Dropped' }) })
  } else if (g.status !== 'Carried') items.push({ label: 'Open again', onClick: () => setGoal(g, { status: 'Open' }) })
  for (const p of ['I', 'II', 'III', 'IV']) if (p !== g.priority) items.push({ label: `Priority ${p}`, onClick: () => setGoal(g, { priority: p }) })
  items.push({ label: 'Rename', onClick: () => { const t = window.prompt('Goal', g.title); if (t && t.trim()) setGoal(g, { title: t.trim() }) } })
  items.push({ label: 'Remove', onClick: () => setGoal(g, { delete: 1 }) })
  return items
}
function toggleSweep() {
  if (editing.value) saveSweep()
  else sweep.value = d.value.plan.mindsweep_md
  editing.value = !editing.value
}
function queueSave() {
  saveState.value = 'Typing…'
  clearTimeout(timer)
  timer = setTimeout(saveSweep, 2000)
}
async function saveSweep() {
  clearTimeout(timer)
  if (sweep.value === d.value.plan.mindsweep_md) return
  const res = await tryCall(() => api('journal.save_month_text', { plan: d.value.plan.name, mindsweep_md: sweep.value }))
  if (res) {
    d.value.plan.mindsweep_md = sweep.value
    saveState.value = 'Saved.'
  }
}
onMounted(() => load())
</script>
<style scoped>
.cols3 { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 0.9fr); gap: 24px; align-items: start; }
@media (max-width: 1100px) { .cols3 { grid-template-columns: 1fr; } }
</style>
