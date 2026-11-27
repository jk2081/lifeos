<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-plan>
    <div class="page-body !gap-4">
      <div>
        <h2 class="text-xl-semibold text-ink-gray-9">{{ monthly ? `Plan ${d ? d.title : 'next month'}` : `Plan the next cycle${d ? ': ' + d.dates.title : ''}` }}</h2>
        <p v-if="monthly" class="text-sm text-ink-gray-6">Goals you carried come first. Add the rest in priority order, each with an area. Nothing is written until you lock the review.</p>
        <p v-else class="text-sm text-ink-gray-6" data-plan-dates>It starts {{ d ? long(d.dates.start) : '' }} and ends {{ d ? long(d.dates.end) : '' }}<template v-if="d?.dates.break_week">, after the break week {{ short(d.dates.break_week[0]) }} – {{ short(d.dates.break_week[1]) }}</template>. Each goal needs a "Done when" and a lead action. Nothing is written until you lock the review.</p>
      </div>
      <Skeleton v-if="!d" class="h-80 w-full" />
      <div v-else class="grid items-start gap-4" :class="monthly && 'lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]'">
        <Card class="flex min-w-0 flex-col gap-3" data-plan-goals>
          <SectionHead>Goals · {{ d.goals.length }}</SectionHead>
          <ol class="flex flex-col gap-3">
            <li v-for="(g, i) in d.goals" :key="g.id" class="flex flex-col gap-2 rounded-5 border border-outline-gray-2 p-3" data-plan-goal :data-carried="g.carried_from ? 1 : 0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="w-5 text-center text-sm tabular-nums text-ink-gray-6" aria-hidden="true">{{ i + 1 }}</span>
                <template v-if="g.carried_from"><span class="min-w-0 flex-1 break-words text-base-medium text-ink-gray-9">{{ g.title }}</span><Badge theme="orange" label="Carried" />
                  <Badge v-if="g.area_name" :label="g.area_name" /></template>
                <FormControl v-else class="min-w-0 flex-1" type="text" :model-value="g.title" placeholder="Goal title" :aria-label="`Goal ${i + 1} title`" data-plan-title
                  @update:model-value="(v) => edit(g, { title: v })" />
                <template v-if="!g.carried_from">
                  <Button size="sm" variant="ghost" icon="lucide-arrow-up" label="Move up" :disabled="!canUp(g)" @click="move(g, -1)" />
                  <Button size="sm" variant="ghost" icon="lucide-arrow-down" label="Move down" :disabled="!canDown(g)" @click="move(g, 1)" />
                  <Button size="sm" variant="ghost" icon="lucide-x" label="Remove goal" data-plan-remove @click="remove(g)" />
                </template>
              </div>
              <div v-if="!g.carried_from" class="grid gap-2 md:grid-cols-2">
                <FormControl type="select" label="Area" :model-value="g.area || ''" placeholder="Choose" :options="areaOptions()" data-plan-area @update:model-value="(v) => edit(g, { area: v })" />
                <FormControl type="select" :label="monthly ? 'Serves (optional)' : 'Serves (optional)'" :model-value="g.serves || ''" :options="[{ label: '—', value: '' }, ...(d.serves_options || goalChoices)]"
                  @update:model-value="(v) => edit(g, { serves: v })" />
              </div>
              <FormControl v-if="monthly && !g.carried_from && store.settings.require_done_when" type="text" label="Done when" :model-value="g.done_when" placeholder="What is true when it is done"
                data-plan-done-when @update:model-value="(v) => edit(g, { done_when: v })" />
              <template v-if="!monthly">
                <FormControl type="text" label="Done when" :model-value="g.done_when" placeholder="What is true when it is done" data-plan-done-when @update:model-value="(v) => edit(g, { done_when: v })" />
                <FormControl v-if="g.carried_from && g.measure_kind === 'Number'" class="max-w-xs" type="number" :label="`Target${g.unit ? ' (' + g.unit + ')' : ''}`" :model-value="g.target"
                  data-plan-target @update:model-value="(v) => edit(g, { target: v })" />
                <div class="flex flex-col gap-2" data-plan-actions>
                  <div class="text-sm-medium text-ink-gray-8">Lead actions</div>
                  <div v-for="(a, k) in g.actions" :key="k" class="grid grid-cols-[minmax(0,1fr)_7rem_auto] items-end gap-2" data-plan-action>
                    <FormControl type="text" :model-value="a.title" placeholder="What you will do" :aria-label="`Action ${k + 1} of ${g.title}`" @update:model-value="(v) => editAction(g, k, { title: v })" />
                    <FormControl type="select" :model-value="String(a.per_week)" :options="PER_WEEK" :aria-label="`How often: ${a.title}`" @update:model-value="(v) => editAction(g, k, { per_week: Number(v) })" />
                    <Button variant="ghost" icon="lucide-x" label="Remove action" @click="removeAction(g, k)" />
                  </div>
                  <div><Button size="sm" icon-left="lucide-plus" label="Add an action" data-plan-add-action @click="addAction(g)" /></div>
                </div>
              </template>
            </li>
          </ol>
          <EmptyState v-if="!d.goals.length" :line="`${monthly ? 'No goals for next month yet.' : 'No goals for the next cycle yet.'} Add one, or carry a goal on in the step before.`" />
          <div><Button icon-left="lucide-plus" label="Add a goal" data-plan-add @click="add" /></div>
        </Card>
        <Card v-if="!monthly && d.focuses?.length" class="flex min-w-0 flex-col gap-3" data-plan-focuses>
          <div>
            <SectionHead>Focuses with no goal this cycle</SectionHead>
            <p class="text-sm text-ink-gray-6">One question each: set a goal this cycle, or just maintain it.</p>
          </div>
          <div v-for="f in d.focuses" :key="f.name" class="flex flex-wrap items-center gap-2 rounded-5 border border-outline-gray-2 p-3" data-plan-focus :data-focus="f.area_name">
            <div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">{{ f.area_name }}</div><div v-if="f.standard" class="text-sm text-ink-gray-6">{{ f.standard }}</div></div>
            <Button size="sm" variant="subtle" icon-left="lucide-plus" label="Set a goal this cycle" data-plan-focus-goal @click="goalFor(f)" />
            <Button size="sm" variant="ghost" label="Just maintain it" data-plan-focus-maintain @click="maintain(f)" />
          </div>
        </Card>
        <Card v-if="monthly" class="flex min-w-0 flex-col gap-3" data-plan-habits>
          <SectionHead>Habits for {{ d.title }}</SectionHead>
          <div v-for="h in d.habits" :key="h.habit" class="grid grid-cols-[minmax(0,1fr)_8rem_auto] items-center gap-2" data-plan-habit>
            <span class="min-w-0 truncate text-ink-gray-9">{{ h.title }}</span>
            <FormControl type="select" :model-value="String(h.days_per_week)" :options="HOW_OFTEN" :aria-label="`How often: ${h.title}`" @update:model-value="(v) => setHabit(h, Number(v))" />
            <Button variant="ghost" icon="lucide-x" label="Remove habit" @click="dropHabit(h)" />
          </div>
          <EmptyState v-if="!d.habits.length">No habits for the month.</EmptyState>
          <FormControl v-if="unused.length" type="select" label="Add a habit" :model-value="''" placeholder="Choose" :options="unused" data-plan-add-habit @update:model-value="addHabit" />
        </Card>
      </div>
    </div>
    <ReviewFooter back label="Next: Reflect" :disabled="!!d?.problems.length" :line="line" :loading="busy" @back="emit('go', decideTab)" @next="next" />
  </div>
</template>
<script setup>
import SectionHead from '@/components/ui/SectionHead.vue'
// Monthly review tab 3 (Plan) and 12-week review tab 3 (Plan the next cycle). The goals carried come first and cannot be removed
// here (change the decision to take one out); goals added here are in the order given. Saved as it is edited.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Badge, Button, FormControl, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'
import { areaOptions, goalOptions, loadLookups } from '@/lib/lookups'
import { long, short } from '@/lib/dates'
import { store } from '@/lib/store'

const emit = defineEmits(['go'])
const r = useReview()
const d = ref(null)
const busy = ref(false)
const monthly = computed(() => r.head?.slug === 'monthly')
const decideTab = computed(() => r.head?.tabs[1].value)
const goalChoices = computed(() => goalOptions())
const PER_WEEK = [1, 2, 3, 4, 5, 6, 7].map((n) => ({ label: `${n} a week`, value: String(n) }))
const HOW_OFTEN = [{ label: 'Every day', value: '7' }, ...[6, 5, 4, 3, 2, 1].map((n) => ({ label: `${n} a week`, value: String(n) }))]
const line = computed(() => {
  const p = d.value?.problems || []
  return p.length ? p[0] + (p.length > 1 ? ` · ${p.length - 1} more` : '') : 'Ready to reflect'
})
const unused = computed(() => (d.value?.habit_options || []).filter((o) => !d.value.habits.some((h) => h.habit === o.value)))

let timer = null
let dirty = false
const extras = () => d.value.goals.filter((g) => !g.carried_from)
const edits = () => Object.fromEntries(d.value.goals.filter((g) => g.carried_from).map((g) => [g.carried_from,
  { done_when: g.done_when, actions: g.actions, target: g.target }]))
// the cycle plan keeps its carried goals' edits as well as the goals added
function payload() {
  const out = { extra: extras().map((g) => ({ id: g.id, title: g.title, area: g.area, serves: g.serves, done_when: g.done_when, actions: g.actions })) }
  if (monthly.value) out.habits = d.value.habits.map((h) => ({ habit: h.habit, days_per_week: h.days_per_week }))
  else { out.edits = edits(); out.maintain = d.value.maintained || [] }
  return out
}
function queue() {
  dirty = true
  clearTimeout(timer)
  timer = setTimeout(save, 900)
}
async function save(confirm = false) {
  clearTimeout(timer)
  if (r.readOnly || r.head?.status === 'Locked' || (!dirty && !confirm)) return
  dirty = false
  const out = await r.act('plan_save', { ...payload(), confirm: confirm ? 1 : 0 })
  if (out) {
    // keep what is being typed: only the problems and the order of ids come back
    d.value.problems = out.problems
    d.value.confirmed = out.confirmed
  }
}
function edit(g, values) { Object.assign(g, values); queue() }
const editAction = (g, k, values) => edit(g, { actions: g.actions.map((a, i) => (i === k ? { ...a, ...values } : a)) })
const addAction = (g) => edit(g, { actions: [...g.actions, { title: '', per_week: 3 }] })
const removeAction = (g, k) => edit(g, { actions: g.actions.filter((_, i) => i !== k) })
function add() {
  d.value.goals.push({ id: 'new' + Date.now(), title: '', area: '', serves: '', done_when: '', actions: monthly.value ? [] : [{ title: '', per_week: 3 }], carried_from: null })
  queue()
}
function goalFor(f) {
  d.value.goals.push({ id: 'new' + Date.now(), title: '', area: f.name, serves: '', done_when: '', actions: [{ title: '', per_week: 3 }], carried_from: null })
  d.value.focuses = d.value.focuses.filter((x) => x.name !== f.name)
  queue()
}
function maintain(f) {
  d.value.maintained = [...(d.value.maintained || []), f.name]
  d.value.focuses = d.value.focuses.filter((x) => x.name !== f.name)
  queue()
}
function remove(g) { d.value.goals = d.value.goals.filter((x) => x !== g); queue() }
const canUp = (g) => { const e = extras(); return e.indexOf(g) > 0 }
const canDown = (g) => { const e = extras(); return e.indexOf(g) < e.length - 1 }
function move(g, by) {
  const carried = d.value.goals.filter((x) => x.carried_from)
  const e = extras()
  const i = e.indexOf(g)
  e.splice(i, 1)
  e.splice(i + by, 0, g)
  d.value.goals = [...carried, ...e]
  queue()
}
function setHabit(h, n) { h.days_per_week = n; queue() }
function dropHabit(h) { d.value.habits = d.value.habits.filter((x) => x !== h); queue() }
function addHabit(v) {
  const o = d.value.habit_options.find((x) => x.value === v)
  if (o) { d.value.habits.push({ habit: o.value, title: o.label, days_per_week: 7 }); queue() }
}
async function next() {
  busy.value = true
  try {
    await save(true)
    emit('go', 'reflect')
  } catch (e) { /* said by act */ } finally { busy.value = false }
}
async function load() { d.value = await r.read('plan') }
watch(() => r.head?.slug, load)
onMounted(async () => { await loadLookups(); await load() })
onBeforeUnmount(() => { if (dirty) save() ; clearTimeout(timer) })
</script>
