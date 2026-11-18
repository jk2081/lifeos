<template>
  <Teleport defer to="#jr-actions">
    <Button v-if="canWrite()" class="max-md:hidden" label="Manage habits" @click="openManage" />
    <Button class="max-md:hidden" :label="yearView ? 'Month view' : 'Year view'" @click="toggleYear" />
    <Button icon="lucide-chevron-left" :label="yearView ? 'Previous year' : 'Previous month'" @click="step(-1)" />
    <Button icon="lucide-chevron-right" :label="yearView ? 'Next year' : 'Next month'" @click="step(1)" />
  </Teleport>
  <div v-if="yearView" class="page-body">
    <div v-if="yearData && yearData.habits.length" class="overflow-hidden rounded-5 border border-outline-gray-2"><div class="scroll-x"><table class="w-full border-collapse text-base">
      <thead><tr class="bg-surface-gray-1 text-xs font-medium text-ink-gray-6"><th class="whitespace-nowrap px-3 py-2 text-left font-medium">Habit</th>
        <th v-for="m in 12" :key="m" class="whitespace-nowrap px-3 py-2 text-right font-medium">{{ MONTHS[m - 1].slice(0, 3) }}</th></tr></thead>
      <tbody><tr v-for="h in yearData.habits" :key="h.habit" class="border-t border-outline-gray-1"><td class="px-3 py-2.5 font-medium text-ink-gray-9">{{ h.title }}</td>
        <td v-for="m in 12" :key="m" class="px-3 py-2.5 text-right tabular-nums">
          <Tooltip :text="h.months[m] ? `${h.months[m].done} of ${h.months[m].target}` : 'Not tracked'"><span>{{ h.months[m] ? h.months[m].percent + '%' : ' ' }}</span></Tooltip></td></tr></tbody>
    </table></div></div>
    <Card v-else-if="yearData"><Empty :title="`No habits were tracked in ${year}.`" hint="A month shows here once its plan lists a habit." /></Card>
    <p class="text-sm text-ink-gray-6">Each habit's percentage for the months it was tracked. A blank month means it was not tracked then.</p>
  </div>
  <div v-else-if="d" class="page-body">
    <div v-if="canWrite()" class="chips md:hidden">
      <Button size="sm" label="Manage habits" @click="openManage" /><Button size="sm" label="Year view" @click="toggleYear" />
    </div>
    <template v-if="d.habits.length">
      <div class="scroll-x">
        <TabButtons :model-value="current.habit" :options="d.habits.map((h) => ({ label: h.title, value: h.habit }))" @update:model-value="(v) => (pick = v)" />
      </div>
      <div class="split">
        <section>
          <div class="mb-2.5 flex items-baseline justify-between gap-2">
            <b class="text-lg-semibold text-ink-gray-9">{{ current.title }}</b>
            <span><b class="font-semibold text-ink-gray-9">{{ current.done }} of {{ current.target }} days</b> <span class="text-sm text-ink-gray-6">{{ current.percent }}%</span></span>
          </div>
          <div class="grid grid-cols-7 gap-1.5">
            <Button v-for="day in d.days_in_month" :key="day" class="!h-11 !w-full !px-0 tabular-nums" size="lg" v-bind="DAY[dayClass(day)]" :disabled="!canWrite() || !tracked(day)" data-habit-day
              :aria-label="`${current.title}, ${day} ${MONTHS[month - 1]}, ${isDone(day) ? 'done' : 'not done'}`" :aria-pressed="isDone(day)" @click="toggle(day)">{{ day }}</Button>
          </div>
          <p class="mt-2.5 text-sm text-ink-gray-6">Seven boxes a row, as in the paper journal. Tap a box to change it.
            <template v-if="current.days_per_week < 7"> Scored against {{ current.days_per_week }} days a week.</template>
            <template v-if="current.removed"> Removed from this month on {{ short(current.tracked_until) }}; later days do not count.</template></p>
        </section>
        <section>
          <SectionHead>{{ isThisMonth ? 'This month so far' : `${MONTHS[month - 1]} ${year}` }}</SectionHead>
          <Card flush>
            <Row v-for="h in d.habits" :key="h.habit" class="!items-center !gap-3.5">
              <span class="w-[84px] flex-none truncate">{{ h.title }}</span>
              <div class="min-w-0 flex-1"><Progress size="sm" :value="h.percent" /></div>
              <span class="min-w-[44px] text-right tabular-nums">{{ h.done }}/{{ h.target }}</span>
            </Row>
          </Card>
        </section>
      </div>
    </template>
    <Card v-else>
      <Empty :title="`No habits are tracked in ${MONTHS[month - 1]} ${year}.`" hint="Each month has its own habit list. A new month starts with last month's list." />
      <Button v-if="canWrite()" variant="solid" label="Manage habits" @click="openManage" />
    </Card>
  </div>

  <Dialog v-model:open="manageOpen" :title="`Habits for ${MONTHS[month - 1]} ${year}`" size="lg"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Save habits', variant: 'solid', onClick: saveManage }]">
    <p class="mb-2.5 text-sm text-ink-gray-6">This list belongs to this month only. Other months keep the habits and ticks they had.</p>
    <div v-for="(h, i) in draft" :key="i" class="mb-1.5 flex items-center gap-2">
      <TextInput v-model="h.title" class="min-w-0 flex-1" :disabled="!!h.habit" :aria-label="`Habit ${i + 1}`" placeholder="Habit" />
      <Select v-model="h.days_per_week" class="w-28" :options="WEEK" :aria-label="`Days a week for habit ${i + 1}`" />
      <Button icon="lucide-arrow-up" label="Move up" :disabled="i === 0" @click="draft.splice(i - 1, 0, draft.splice(i, 1)[0])" />
      <Button icon="lucide-x" label="Remove from this month" @click="draft.splice(i, 1)" />
    </div>
    <div class="chips mt-2">
      <Button size="sm" variant="outline" icon-left="lucide-plus" label="new habit" @click="draft.push({ title: '', days_per_week: 7 })" />
      <Button v-for="h in unused" :key="h.name" size="sm" variant="outline" icon-left="lucide-plus" :label="h.title" @click="draft.push({ habit: h.name, title: h.title, days_per_week: 7 })" />
    </div>
  </Dialog>
</template>
<script setup>
// Habits of one month: a box for each day of the chosen habit (a frappe-ui Button whose variant says its state), and the year table.
import { computed, onMounted, ref } from 'vue'
import { Button, Dialog, Progress, Select, TabButtons, TextInput, Tooltip } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { MONTHS, parse, short } from '@/lib/dates'

const emit = defineEmits(['sub'])
const now = parse(store.today)
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)
const d = ref(null)
const pick = ref('')
const yearView = ref(false)
const yearData = ref(null)
const manageOpen = ref(false)
const draft = ref([])
const library = ref([])
const WEEK = [1, 2, 3, 4, 5, 6, 7].map((n) => ({ label: `${n} a week`, value: n }))
// the Button that draws each state of a day: done is solid, today is blue, missed is filled, untracked days are disabled
const DAY = { d: { variant: 'solid' }, t: { variant: 'outline', theme: 'blue', class: '!text-ink-blue-8' }, m: { variant: 'subtle' }, f: { variant: 'outline' }, off: { variant: 'outline' } }
const pad = (n) => String(n).padStart(2, '0')
const iso = (day) => `${year.value}-${pad(month.value)}-${pad(day)}`
const current = computed(() => d.value.habits.find((h) => h.habit === pick.value) || d.value.habits[0])
const isThisMonth = computed(() => year.value === now.getFullYear() && month.value === now.getMonth() + 1)
const isDone = (day) => current.value.done_days.includes(day)
// a day counts from the day the habit was added to the day it was removed, and never before it has come
const tracked = (day) => iso(day) >= current.value.tracked_from && iso(day) <= current.value.tracked_until && iso(day) <= d.value.today
const unused = computed(() => library.value.filter((h) => !draft.value.some((x) => x.habit === h.name)))

function dayClass(day) {
  const date = iso(day)
  if (!tracked(day)) return 'off'
  if (isDone(day)) return 'd'
  if (date === d.value.today) return 't'
  if (date < d.value.today) return 'm'
  return 'f'
}
function recount(h) {
  h.done = h.done_days.length
  h.percent = h.target ? Math.min(100, Math.round((100 * h.done) / h.target)) : 0
}
function toggle(day) {
  const h = current.value
  const was = isDone(day)
  const flip = (on) => { h.done_days = on ? [...h.done_days, day].sort((a, b) => a - b) : h.done_days.filter((x) => x !== day); recount(h) }
  optimistic(() => flip(!was), () => flip(was), () => api('journal.toggle_habit', { habit: h.habit, date: iso(day), done: was ? 0 : 1 })).catch(() => {})
}
async function load() {
  if (yearView.value) {
    yearData.value = await tryCall(() => api('journal.habits_year', { space: store.space, year: year.value }))
    emit('sub', `Habits in ${year.value}`)
    return
  }
  const res = await tryCall(() => api('journal.habits', { space: store.space, year: year.value, month: month.value }))
  if (res) d.value = res
  emit('sub', `${MONTHS[month.value - 1]} ${year.value}`)
}
function step(n) {
  if (yearView.value) year.value += n
  else {
    const m = month.value + n
    if (m < 1) { month.value = 12; year.value-- } else if (m > 12) { month.value = 1; year.value++ } else month.value = m
  }
  load()
}
function toggleYear() {
  yearView.value = !yearView.value
  load()
}
async function openManage() {
  yearView.value = false
  library.value = (await tryCall(() => api('journal.habit_library', { space: store.space }))) || []
  draft.value = (d.value?.habits || []).filter((h) => !h.removed).map((h) => ({ habit: h.habit, title: h.title, days_per_week: h.days_per_week }))
  manageOpen.value = true
}
async function saveManage() {
  const res = await tryCall(() => api('journal.set_month_habits', { space: store.space, year: year.value, month: month.value, habits: draft.value }), 'Habits saved for this month.')
  if (res) {
    d.value = res
    manageOpen.value = false
  }
}
onMounted(load)
</script>
<style scoped>
/* geometry only: the day boxes beside the month's totals, stacked on a phone */
.split { display: grid; grid-template-columns: minmax(0, 420px) minmax(0, 1fr); gap: 32px; align-items: start; }
@media (max-width: 767px) { .split { grid-template-columns: minmax(0, 1fr); gap: 20px; } }
</style>
