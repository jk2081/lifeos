<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-goals>
    <div class="page-body !gap-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-xl-semibold text-ink-gray-9">Where your goals stand, and next week</h2>
          <p class="text-sm text-ink-gray-6">One next action per goal, already suggested. Star exactly three. Click a row to change anything.</p>
        </div>
        <div v-if="t" class="flex gap-6 max-md:w-full max-md:flex-col max-md:gap-3">
          <Stat class="w-52 max-md:w-full !border-0 !bg-transparent !p-0" :label="t.score ? `Week ${t.score.week} score` : 'Week score'" :value="t.score ? Math.round(t.score.percent) + '%' : '—'" data-goals-score>
            <span class="flex items-baseline gap-2">{{ t.score ? Math.round(t.score.percent) + '%' : '—' }}<span class="text-sm font-normal text-ink-gray-7">target {{ t.target }}%</span></span>
            <template #sub>
              <Progress size="sm" :value="t.score ? Math.min(100, t.score.percent) : 0" :aria-label="`Week score against a target of ${t.target}%`" />
            </template>
          </Stat>
          <Stat class="w-56 max-md:w-full !border-0 !bg-transparent !p-0" label="Goal work planned" :value="hours(t.capacity.planned_minutes)" :warn="!!t.capacity.over" data-goals-capacity :data-over="t.capacity.over ? 1 : 0">
            <span class="flex items-baseline gap-2">{{ hours(t.capacity.planned_minutes) }}<span class="text-sm font-normal" :class="t.capacity.over ? 'text-ink-amber-9' : 'text-ink-gray-7'" data-goals-capacity-line>{{ t.capacity.over ? `planned, ${hours(t.capacity.free_minutes)} free` : `of ${hours(t.capacity.free_minutes)} free` }}</span></span>
            <template #sub>
              <Progress size="sm" :class="t.capacity.over && 'capacity-over'" :value="t.capacity.free_minutes ? Math.min(100, (100 * t.capacity.planned_minutes) / t.capacity.free_minutes) : 100"
                :aria-label="`${hours(t.capacity.planned_minutes)} planned of ${hours(t.capacity.free_minutes)} free`" />
            </template>
          </Stat>
        </div>
      </div>
      <Skeleton v-if="!t" class="h-80 w-full" />
      <div v-else class="grid items-start gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <Card class="flex min-w-0 flex-col" flush data-goals-list>
          <div class="flex flex-wrap items-baseline justify-between gap-2 pb-1 pt-3">
            <SectionHead class="!mb-0">{{ t.cycle ? 'This 12 Week Year' : 'Goals this week' }} · {{ t.rows.length }} goal{{ t.rows.length === 1 ? '' : 's' }}</SectionHead>
            <span class="text-sm text-ink-gray-6" data-stars-used>{{ t.stars.length }} of {{ t.needed }} stars used</span>
          </div>
          <!-- the rows scroll inside the card only when there are more than fit (the page itself never scrolls) -->
          <div class="md:max-h-[calc(100vh-330px)] md:overflow-y-auto" data-goal-rows>
          <Row bare v-for="g in t.rows" :key="g.goal" class="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 py-2 hover:bg-surface-gray-1 md:grid-cols-[2rem_11rem_7rem_minmax(0,1fr)_auto_auto] -mx-4 px-4"
            :class="g.plan.skip && 'opacity-80'" data-goal-row :data-goal="g.goal" :data-star="g.star ? 1 : 0" :data-skipped="g.plan.skip ? 1 : 0">
            <button type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="`Plan ${g.title}`" @click="open(g.goal)" />
            <Button class="relative" :variant="g.star ? 'subtle' : 'ghost'" size="sm" icon="lucide-star" :label="g.star ? `Unstar ${g.title}` : `Star ${g.title}`"
              :class="g.star ? '!bg-surface-amber-2 !text-ink-amber-9' : '!text-ink-gray-6'" :disabled="!!g.plan.skip" data-goal-star-btn @click="star(g)" />
            <div class="min-w-0">
              <div class="truncate text-base-medium text-ink-gray-9" :title="g.title">{{ g.title }}</div>
              <div class="flex min-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap">
                <Badge v-if="g.mark" size="sm" :theme="MARK[g.mark]" :label="g.mark" data-goal-mark />
                <a v-if="g.needs_finish_line" href="#" class="relative truncate text-sm text-ink-amber-9 hover:underline focus-visible:focus-ring" data-goal-needs-finish @click.prevent="open(g.goal, 'finish')">needs a finish line</a>
                <a v-else-if="g.readings" href="#" class="relative truncate text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" data-goal-readings-link @click.prevent="open(g.goal)">{{ g.readings }} reading{{ g.readings === 1 ? '' : 's' }} to confirm</a>
              </div>
            </div>
            <div class="max-md:hidden" data-goal-progress>
              <Progress size="sm" :value="g.progress.percent || 0" :aria-label="g.progress.label" />
              <div class="mt-0.5 truncate text-sm text-ink-gray-7">{{ g.progress.label }}</div>
            </div>
            <div class="min-w-0 max-md:col-span-3 max-md:col-start-2 max-md:row-start-2">
              <div class="text-xs text-ink-gray-6">{{ g.plan.skip ? 'Skipped this week' : 'Next action' }}</div>
              <div class="truncate text-base text-ink-gray-9" data-goal-next-action>{{ g.plan.skip || g.plan.next_action || '—' }}</div>
            </div>
            <template v-if="!g.plan.skip">
              <Button class="relative max-md:col-start-2 max-md:row-start-3 max-md:justify-self-start" :label="whenLabel(g.plan)" data-goal-when-btn @click="open(g.goal)" />
              <Button class="relative max-md:col-start-3 max-md:row-start-1" :label="g.plan.who || 'Me'" data-goal-who-btn @click="open(g.goal)" />
            </template>
          </Row>
          </div>
          <div v-if="t.others.n" class="flex items-center justify-between gap-2 py-2.5" data-goals-others>
            <span class="min-w-0 truncate text-sm text-ink-gray-7">▸ {{ t.others.n }} other goal{{ t.others.n === 1 ? '' : 's' }} in progress · {{ othersLine }}</span>
            <Button variant="ghost" class="!text-ink-blue-8" label="Plan any" data-goals-plan-any @click="othersOpen = true" />
          </div>
          <EmptyState v-if="!t.rows.length">No 12 Week Year is active. Plan any of your other goals for the coming week.</EmptyState>
        </Card>
        <Card class="flex min-w-0 flex-col max-lg:hidden" flush data-goals-calendar>
          <div class="flex items-baseline justify-between py-2.5">
            <SectionHead class="!mb-0">Next week</SectionHead>
            <RouterLink class="text-base text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ path: '/today/week', query: { view: 'calendar', tab: undefined } }"
              data-open-full-week>Open the full week</RouterLink>
          </div>
          <WeekGlance :g="t.glance" class="-mx-4" @open="open" @ref="openRef" />
        </Card>
        <Button class="lg:hidden" icon-left="lucide-calendar" label="Next week" data-goals-week-btn @click="weekOpen = true" />
      </div>
    </div>
    <!-- a goal opens in the Drawer, with this week's plan on top (GoalPane); the two lists below are dialogs -->
    <Dialog v-model:open="othersOpen" title="Other goals in progress" size="md" data-dialog="other-goals">
      <p class="mb-2 text-sm text-ink-gray-6">Planning one adds it to this week's rows.</p>
      <Row bare v-for="o in t?.others.rows || []" :key="o.goal" class="flex items-center gap-2 py-2" data-other-goal>
        <div class="min-w-0 flex-1"><div class="truncate text-base text-ink-gray-9">{{ o.title }}</div><div class="text-sm text-ink-gray-6">{{ o.horizon }}</div></div>
        <Button size="sm" label="Plan" data-other-goal-plan @click="addOther(o)" />
      </Row>
    </Dialog>
    <Dialog v-model:open="weekOpen" title="Next week" size="xl" data-dialog="next-week">
      <WeekGlance v-if="t" :g="t.glance" @open="(g) => { weekOpen = false; open(g) }" @ref="(r) => { weekOpen = false; openRef(r) }" />
    </Dialog>
    <ReviewFooter back label="Next: Reflect" :disabled="!t?.ready.ok" :line="footerLine" @back="emit('go', 'tasks')" @next="emit('go', 'reflect')" />
  </div>
</template>
<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
import Row from '@/components/ui/Row.vue'
import Stat from '@/components/ui/Stat.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
// Tab 3, Goals (boards 31 and 32): the cycle's goals in the lens of the week (star, mark, progress, next action, when and
// length, who), the other goals folded into one line, the week's score and goal work against free hours, and next week at a
// glance. Next: Reflect opens when every cycle goal has a next action or a skip, and exactly three are starred.
import { computed, onMounted, ref, watch } from 'vue'
import { Badge, Button, Dialog, Progress, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { onRecordChanged, openRef } from '@/lib/pane'
import WeekGlance from '@/components/review/WeekGlance.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'
import { time, weekday } from '@/lib/dates'

const emit = defineEmits(['go'])
const r = useReview()
const t = ref(null)
const othersOpen = ref(false)
const weekOpen = ref(false)
const MARK = { 'No ticks': 'red', Slipping: 'amber', 'On track': 'green' }
const hours = (m) => `${Math.round((m / 60) * 10) / 10} h`
const whenLabel = (p) => (p.slot ? `${weekday(p.slot, 3)} ${time(p.slot)} · ${p.minutes}m` : 'No set time')
const othersLine = computed(() => [...t.value.others.titles, ...(t.value.others.n > 2 ? [`+${t.value.others.n - 2}`] : [])].join(', '))
const footerLine = computed(() => {
  if (!t.value) return ''
  const n = t.value.to_schedule
  const sched = `${n} task${n === 1 ? '' : 's'} will be scheduled when you lock the week`
  return t.value.ready.ok ? sched : `${t.value.ready.left.join(' · ')} · ${sched}`
})

async function load() { t.value = await r.read('goals') }
// a goal opens in the Drawer with the review's plan on top (`review=1`); "needs a finish line" opens it on the finish line
function open(goal, why = '') { openRef('goal:' + goal, { review: 1, ...(why ? { focus: why } : {}) }) }
async function star(g) { await r.act('goal_star', { goal: g.goal, on: g.star ? 0 : 1 }); load() }
async function addOther(o) { await r.act('goal_add', { goal: o.goal }); othersOpen.value = false; load() }
watch(() => r.head?.name, load)
onMounted(load)
onRecordChanged(load) // the goal's plan, saved in the Drawer
</script>
<style scoped>
/* the planned bar turns amber when goal work is more than the free hours (frappe-ui's Progress has no tone prop) */
.capacity-over :deep([role="progressbar"] > div), .capacity-over :deep(.bg-surface-gray-7) { background-color: var(--surface-amber-7); }
</style>
