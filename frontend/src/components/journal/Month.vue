<template>
  <Teleport to="#jr-actions">
    <Button icon="lucide-chevron-left" label="Previous month" @click="step(-1)" />
    <Button icon="lucide-chevron-right" label="Next month" @click="step(1)" />
  </Teleport>
  <div v-if="d" class="page-body">
    <Card v-if="!d.plan">
      <Empty :title="`No plan for ${MONTHS[month - 1]} ${year} yet.`" hint="A new plan starts with last month's habits. Goals and the mindsweep start empty." />
      <Button v-if="canWrite()" variant="solid" label="Start this month's plan" @click="load(true)" />
    </Card>
    <div v-else class="cols3">
      <section>
        <SectionHead>Goals <span class="font-normal text-ink-gray-6">{{ doneCount }} of {{ d.plan.goals.length }} done</span></SectionHead>
        <Card flush>
          <Row v-for="g in d.plan.goals" :key="g.row" class="!items-center">
            <Checkbox :model-value="g.status === 'Done'" :disabled="!canWrite() || g.status === 'Carried'" :aria-label="'Done: ' + g.title"
              @update:model-value="setGoal(g, { status: g.status === 'Done' ? 'Open' : 'Done' })" />
            <Badge class="min-w-[26px] justify-center" :label="g.priority || '·'" />
            <div class="min-w-0 flex-1">
              <div class="break-words text-base-medium" :class="g.status === 'Done' || g.status === 'Dropped' ? 'text-ink-gray-6 line-through' : g.status === 'Carried' ? 'text-ink-gray-6' : 'text-ink-gray-9'">
                {{ g.title }}<Tooltip v-if="g.status === 'Carried'" text="Carried to next month"><span> →</span></Tooltip></div>
              <div class="text-sm text-ink-gray-6">{{ [g.area_name, g.carried_from ? 'carried from last month' : '', g.status === 'Carried' ? 'carried forward' : '', g.status === 'Dropped' ? 'dropped' : ''].filter(Boolean).join(' · ') }}
                <a v-if="g.task" href="#" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" @click.prevent="openRef('task:' + g.task)">{{ g.area_name || g.carried_from ? '· ' : '' }}task</a></div>
            </div>
            <Dropdown v-if="canWrite()" :options="goalMenu(g)"><Button variant="ghost" icon="lucide-ellipsis" :label="'Actions for ' + g.title" /></Dropdown>
          </Row>
          <Empty v-if="!d.plan.goals.length" title="No goals this month." hint="Add what you want done this month, with a priority from I to IV." />
          <Row v-if="canWrite()">
            <Select v-model="newPriority" class="w-16 flex-none" :options="PRIORITY" aria-label="Priority" />
            <TextInput v-model="newGoal" class="min-w-0 flex-1" placeholder="Add a goal for the month" aria-label="New goal" @keydown.enter="addGoal" />
          </Row>
        </Card>
      </section>
      <section>
        <SectionHead>Mindsweep <template v-if="canWrite()" #action><Button variant="ghost" size="sm" :label="editing ? 'Done' : 'Edit'" @click="toggleSweep" /></template></SectionHead>
        <Card>
          <Textarea v-if="editing" v-model="sweep" :rows="16" aria-label="Mindsweep" placeholder="Everything on your mind. Use ## for a topic and ★ to star one." @update:model-value="queueSave" />
          <Md v-else-if="d.plan.mindsweep_md" :text="d.plan.mindsweep_md" />
          <Empty v-else title="The mindsweep is empty." hint="A free page for everything on your mind this month. Use ## for a topic and ★ to star one." />
        </Card>
        <p v-if="editing" class="mt-2 text-sm text-ink-gray-6">{{ saveState }}</p>
      </section>
      <section>
        <SectionHead>Habits <template #action><Button variant="ghost" size="sm" label="Open" route="/journal/habits" /></template></SectionHead>
        <Card flush>
          <Row v-for="h in d.habits.habits" :key="h.habit" class="!items-center">
            <span class="w-[84px] flex-none truncate">{{ h.title }}</span>
            <div class="min-w-0 flex-1"><Progress size="sm" :value="h.percent" /></div><span class="tabular-nums">{{ h.done }}/{{ h.target }}</span>
          </Row>
          <Empty v-if="!d.habits.habits.length" title="No habits this month." hint="Choose the habits to track under Habits, Manage habits." />
        </Card>
        <SectionHead class="mt-6">Latest check-in <template #action><Button variant="ghost" size="sm" label="Open" route="/journal/checkins" /></template></SectionHead>
        <Card flush>
          <template v-if="d.latest_checkin">
            <Row><span class="text-sm text-ink-gray-6">{{ long(d.latest_checkin.date, true) }}</span></Row>
            <Row v-for="s in d.latest_checkin.scores" :key="s.dimension"><span class="min-w-0 flex-1">{{ s.dimension_name }}</span>
              <span class="whitespace-nowrap text-sm text-ink-gray-6">{{ range(s.habits_low, s.habits_high) }} · {{ range(s.situation_low, s.situation_high) }}</span></Row>
          </template>
          <Empty v-else title="No check-in yet." hint="Score each life dimension under Check-ins." />
        </Card>
      </section>
    </div>
  </div>
</template>
<script setup>
import { openRef } from '@/lib/pane'
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Checkbox, Dropdown, Progress, Select, Textarea, TextInput, Tooltip, dialog, toast } from 'frappe-ui'
import Md from '@/components/Md.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { MONTHS, long, parse } from '@/lib/dates'

const emit = defineEmits(['sub'])
const PRIORITY = [{ label: '–', value: '' }, 'I', 'II', 'III', 'IV']
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
  const res = await tryCall(() => api('journal.month', { space: store.space, year: year.value, month: month.value, create: create ? 1 : 0, area: store.lensArea || undefined }))
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
  const res = await tryCall(() => api('journal.save_month_goal', { plan: d.value.plan.name, title, priority: newPriority.value || '' }))
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
  items.push({ label: 'Rename', onClick: () => rename(g) })
  items.push({ label: 'Remove', onClick: () => setGoal(g, { delete: 1 }) })
  return items
}
function rename(g) {
  dialog.prompt({
    title: 'Rename goal',
    confirmLabel: 'Rename',
    fields: [{ name: 'title', label: 'Goal', defaultValue: g.title, required: true }],
    onConfirm: async ({ values }) => {
      const t = String(values.title || '').trim()
      if (t) await setGoal(g, { title: t })
    },
  })
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
/* geometry only: three columns of unequal width, one column when narrow */
.cols3 { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 0.9fr); gap: 24px; align-items: start; }
@media (max-width: 1100px) { .cols3 { grid-template-columns: minmax(0, 1fr); } }
</style>
