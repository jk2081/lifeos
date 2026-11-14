<template>
  <Teleport to="#jr-actions">
    <button v-if="canWrite()" class="bt s only-desktop" type="button" @click="openManage">Manage habits</button>
    <button class="bt s only-desktop" type="button" @click="toggleYear">{{ yearView ? 'Month view' : 'Year view' }}</button>
    <button class="bt s ic" type="button" :aria-label="yearView ? 'Previous year' : 'Previous month'" @click="step(-1)"><Ico d="m15 6-6 6 6 6" stroke="2" /></button>
    <button class="bt s ic" type="button" :aria-label="yearView ? 'Next year' : 'Next month'" @click="step(1)"><Ico d="m9 6 6 6-6 6" stroke="2" /></button>
  </Teleport>
  <div v-if="yearView" class="bd">
    <div v-if="yearData && yearData.habits.length" class="tblwrap"><div class="tblscroll"><table class="tbl">
      <thead><tr><th>Habit</th><th v-for="m in 12" :key="m" style="text-align: right">{{ MONTHS[m - 1].slice(0, 3) }}</th></tr></thead>
      <tbody><tr v-for="h in yearData.habits" :key="h.habit"><td style="font-weight: 500">{{ h.title }}</td>
        <td v-for="m in 12" :key="m" style="text-align: right; font-variant-numeric: tabular-nums" :title="h.months[m] ? `${h.months[m].done} of ${h.months[m].target}` : 'Not tracked'">
          {{ h.months[m] ? h.months[m].percent + '%' : '' }}</td></tr></tbody>
    </table></div></div>
    <div v-else-if="yearData" class="cd"><Empty :title="`No habits were tracked in ${year}.`" hint="A month shows here once its plan lists a habit." /></div>
    <p class="mt" style="margin: 0">Each habit's percentage for the months it was tracked. A blank month means it was not tracked then.</p>
  </div>
  <div v-else-if="d" class="bd">
    <div class="chips only-phone" v-if="canWrite()">
      <button class="ch" type="button" @click="openManage">Manage habits</button><button class="ch" type="button" @click="toggleYear">Year view</button>
    </div>
    <template v-if="d.habits.length">
      <div class="chips">
        <button v-for="h in d.habits" :key="h.habit" class="ch" :class="{ on: h.habit === current.habit }" type="button" @click="pick = h.habit">{{ h.title }}</button>
      </div>
      <div class="split">
        <section>
          <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 10px">
            <b style="font-size: 16px; font-weight: 600">{{ current.title }}</b>
            <span><b style="font-weight: 600">{{ current.done }} of {{ current.target }} days</b> <span class="mt">{{ current.percent }}%</span></span>
          </div>
          <div class="days">
            <button v-for="day in d.days_in_month" :key="day" class="dy" :class="dayClass(day)" type="button" :disabled="!canWrite() || !tracked(day)"
              :aria-label="`${current.title}, ${day} ${MONTHS[month - 1]}, ${isDone(day) ? 'done' : 'not done'}`" :aria-pressed="isDone(day)" @click="toggle(day)">{{ day }}</button>
          </div>
          <p class="mt" style="margin: 10px 0 0">Seven boxes a row, as in the paper journal. Tap a box to change it.
            <template v-if="current.days_per_week < 7"> Scored against {{ current.days_per_week }} days a week.</template>
            <template v-if="current.removed"> Removed from this month on {{ short(current.tracked_until) }}; later days do not count.</template></p>
        </section>
        <section>
          <h2 class="sh">{{ isThisMonth ? 'This month so far' : `${MONTHS[month - 1]} ${year}` }}</h2>
          <div class="cd list">
            <div v-for="h in d.habits" :key="h.habit" class="rw" style="align-items: center; gap: 14px">
              <span style="width: 84px; flex: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ h.title }}</span>
              <div class="br"><i :style="`width: ${h.percent}%`"></i></div>
              <span style="font-variant-numeric: tabular-nums; min-width: 44px; text-align: right">{{ h.done }}/{{ h.target }}</span>
            </div>
          </div>
        </section>
      </div>
    </template>
    <div v-else class="cd">
      <Empty :title="`No habits are tracked in ${MONTHS[month - 1]} ${year}.`" hint="Each month has its own habit list. A new month starts with last month's list." />
      <button v-if="canWrite()" class="bt p" type="button" @click="openManage">Manage habits</button>
    </div>
  </div>

  <Dialog v-model="manageOpen" :title="`Habits for ${MONTHS[month - 1]} ${year}`" size="lg">
    <p class="mt" style="margin: 0 0 10px">This list belongs to this month only. Other months keep the habits and ticks they had.</p>
    <div v-for="(h, i) in draft" :key="i" style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center">
      <input v-model="h.title" class="inp" style="flex: 1" :disabled="!!h.habit" :aria-label="`Habit ${i + 1}`" placeholder="Habit" />
      <select v-model.number="h.days_per_week" class="inp" :aria-label="`Days a week for habit ${i + 1}`"><option v-for="n in 7" :key="n" :value="n">{{ n }} a week</option></select>
      <button class="bt s ic" type="button" aria-label="Move up" :disabled="i === 0" @click="draft.splice(i - 1, 0, draft.splice(i, 1)[0])">↑</button>
      <button class="bt s ic" type="button" aria-label="Remove from this month" @click="draft.splice(i, 1)">×</button>
    </div>
    <div class="chips" style="margin-top: 8px">
      <button class="ch sm add" type="button" @click="draft.push({ title: '', days_per_week: 7 })">+ new habit</button>
      <button v-for="h in unused" :key="h.name" class="ch sm add" type="button" @click="draft.push({ habit: h.name, title: h.title, days_per_week: 7 })">+ {{ h.title }}</button>
    </div>
    <template #actions><div style="display: flex; gap: 8px; justify-content: flex-end">
      <button class="bt s" type="button" @click="manageOpen = false">Cancel</button><button class="bt p" type="button" @click="saveManage">Save habits</button></div></template>
  </Dialog>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Dialog } from 'frappe-ui'
import Ico from '@/components/Ico.vue'
import Empty from '@/components/Empty.vue'
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
const pad = (n) => String(n).padStart(2, '0')
const iso = (day) => `${year.value}-${pad(month.value)}-${pad(day)}`
const current = computed(() => d.value.habits.find((h) => h.habit === pick.value) || d.value.habits[0])
const isThisMonth = computed(() => year.value === now.getFullYear() && month.value === now.getMonth() + 1)
const isDone = (day) => current.value.done_days.includes(day)
const tracked = (day) => iso(day) >= current.value.tracked_from && iso(day) <= current.value.tracked_until
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
.split { display: grid; grid-template-columns: minmax(0, 420px) minmax(0, 1fr); gap: 32px; align-items: start; }
.days { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }
.dy { height: 44px; border-radius: 10px; border: 1px solid var(--line3); background: var(--bg); color: var(--ink); font: 500 14px Inter, system-ui, sans-serif; font-variant-numeric: tabular-nums; padding: 0; cursor: pointer; }
.dy.d { background: var(--ink); border-color: var(--ink); color: var(--bg); }
.dy.m { background: var(--fill); border-color: var(--fill); color: var(--mut); }
.dy.t { border: 2px solid var(--accent); color: var(--accent); font-weight: 700; }
.dy.f { color: var(--mut); }
.dy.off { border-style: dashed; color: var(--line4); cursor: default; }
@media (max-width: 800px) { .split { grid-template-columns: 1fr; gap: 20px; } }
</style>
