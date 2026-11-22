<template>
  <PageHead title="Goals" :sub="sub">
    <Button v-if="writable" variant="solid" icon-left="lucide-plus" label="Goal" data-new-goal @click="addGoal('')" />
  </PageHead>
  <div class="page-body flex max-w-6xl flex-col gap-4" data-goals-by-area :data-loaded="loaded ? 1 : 0">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2" data-goal-controls>
      <TabButtons :model-value="show" :options="SHOWS" data-goal-show @update:model-value="(v) => go({ show: v })" />
      <Select class="w-44" :model-value="sort" :options="SORTS" aria-label="Sort goals" data-goal-sort @update:model-value="(v) => go({ sort: v })" />
    </div>
    <!-- the old Open band's goal numbers (issue 55): goals in progress, open-ended goals and the idle ones, each as the helper counts them -->
    <p v-if="numbers && (numbers.goals.n || numbers.open_goals.n)" class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-7" data-goal-numbers>
      <span>Goals in progress <b class="tabular-nums text-ink-gray-9" data-goal-number="goals">{{ numbers.goals.n }}</b></span>
      <span>Open-ended goals <b class="tabular-nums text-ink-gray-9" data-goal-number="open_goals">{{ numbers.open_goals.n }}</b></span>
      <span>idle {{ numbers.rules.stuck_after_days }}+ days <b class="tabular-nums text-ink-gray-9" data-goal-number="idle_goals">{{ numbers.idle_goals.n }}</b></span>
    </p>
    <!-- one chip for each of the seven areas; an area that is off is dimmed and has no section -->
    <nav class="flex flex-wrap items-center gap-2" aria-label="Areas" data-area-chips>
      <Button :variant="only ? 'subtle' : 'solid'" :label="`All ${data?.total ?? 0}`" data-area-chip="all" @click="only = ''" />
      <Button v-for="s in sections" :key="s.area" :variant="only === s.area ? 'solid' : 'subtle'" :label="`${s.area_name} ${s.count}`" :data-area-chip="s.area_name" @click="only = s.area">
        <template #prefix><span class="size-2 rounded-full" :class="dotClass(s)" aria-hidden="true" /></template>
      </Button>
      <Button v-for="a in data?.off || []" :key="a.name" variant="outline" disabled :label="`${a.area_name} off`" :data-area-chip-off="a.area_name" />
      <RouterLink class="text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" to="/settings?tab=areas" data-manage-areas>Manage areas</RouterLink>
    </nav>

    <Card v-if="loaded && data && !data.sections.length && !data.no_area.length" class="py-2" data-goals-none>
      <Empty title="No areas are on.">
        <p class="mt-1">Goals are kept under the areas of your life. Switch an area on and its goals appear here.</p>
        <Button class="mt-3" variant="solid" label="Manage areas" route="/settings?tab=areas" />
      </Empty>
    </Card>
    <Card v-else-if="loaded && data && !data.total" class="py-2" data-goals-empty>
      <Empty :title="HINT[show][0]">
        <p class="mt-1">{{ HINT[show][1] }}</p>
        <Button v-if="writable" class="mt-3" variant="solid" icon-left="lucide-plus" label="Goal" data-goals-empty-add @click="addGoal('')" />
      </Empty>
    </Card>
    <section v-for="s in (data?.total ? shown : [])" :key="s.area" class="flex flex-col gap-2" data-area-section :data-area="s.area_name">
      <div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 pb-2">
        <span class="size-2.5 rounded-full" :class="dotClass(s)" aria-hidden="true" />
        <h2 class="text-base-medium text-ink-gray-9">{{ s.area_name }}</h2>
        <span class="text-sm text-ink-gray-6" data-area-line>{{ areaLine(s) }}</span>
        <Button v-if="writable && s.count" class="ml-auto" size="sm" variant="ghost" icon-left="lucide-plus" label="Goal" :aria-label="`New goal in ${s.area_name}`" @click="addGoal(s.area)" />
      </div>
      <div v-if="!s.count" class="flex flex-wrap items-center gap-3 py-1" data-area-empty>
        <span class="text-sm text-ink-gray-6">No goals yet</span>
        <Button v-if="writable" size="sm" variant="subtle" icon-left="lucide-plus" label="Goal" :aria-label="`New goal in ${s.area_name}`" data-area-add @click="addGoal(s.area)" />
      </div>
      <template v-for="g in s.groups" :key="g.area?.name || 'direct'">
        <h3 v-if="g.area" class="mt-1 text-sm-medium text-ink-gray-7" data-part-head :data-part="g.area.area_name">{{ g.area.area_name }}</h3>
        <ul class="flex flex-col gap-2" :data-goal-list="s.area_name">
          <li v-for="(goal, i) in g.goals" :key="goal.name" class="group" :draggable="canDrag" data-goal-card :data-goal="goal.name" :data-area-name="s.area_name" :data-part-name="g.area?.area_name || ''"
            @dragstart="dragged = goal" @dragover.prevent="over(g.goals, goal)" @drop.prevent="drop(g.goals)" @dragend="dragged = null">
            <Card class="relative flex flex-col gap-2 hover:bg-surface-gray-1 md:grid md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.3fr)_8rem] md:items-start md:gap-4">
              <RouterLink class="absolute inset-0 rounded-5 focus-visible:focus-ring" :to="`/goals/${goal.name}`" :aria-label="`Open ${goal.title}`" data-goal-open />
              <div class="min-w-0">
                <div class="break-words text-base-medium text-ink-gray-9" data-goal-title>{{ goal.title }}</div>
                <div class="text-sm text-ink-gray-6" data-goal-done-when>{{ doneWhen(goal) }}</div>
                <div v-if="goal.serves_title" class="truncate text-sm text-ink-gray-6" data-goal-serves>Serves {{ goal.serves_title }}</div>
              </div>
              <div class="flex min-w-0 flex-col gap-1" data-goal-progress>
                <Progress size="sm" :value="Math.round(goal.progress.percent || 0)" />
                <span class="truncate text-sm tabular-nums text-ink-gray-7">{{ goal.progress.label }}</span>
              </div>
              <div class="min-w-0 text-sm" data-goal-next>
                <div class="truncate text-ink-gray-9" data-goal-next-title>{{ goal.next_action ? goal.next_action.title : 'No next action' }}</div>
                <div class="truncate text-ink-gray-6"><span v-if="goal.next_action && nextWhen(goal.next_action)">{{ nextWhen(goal.next_action) }} · </span><span data-goal-open-tasks :data-count="goal.open_tasks">{{ goal.open_tasks }} open task{{ goal.open_tasks === 1 ? '' : 's' }}</span></div>
              </div>
              <div class="flex flex-wrap items-center gap-2 md:justify-end" data-goal-week>
                <Badge v-if="goal.week" theme="blue" :label="`Week ${goal.week} · ${Math.round(goal.score ?? 0)}%`" data-goal-score :data-score="Math.round(goal.score ?? 0)" />
                <span v-else-if="goal.target_date" class="text-sm text-ink-gray-6">by {{ short(goal.target_date, true) }}</span>
                <template v-if="canDrag">
                  <Button class="relative md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100" size="sm" variant="ghost" icon="lucide-chevron-up" :disabled="i === 0" :aria-label="`Move ${goal.title} up`" data-goal-up @click="move(g.goals, i, -1)" />
                  <Button class="relative md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100" size="sm" variant="ghost" icon="lucide-chevron-down" :disabled="i === g.goals.length - 1" :aria-label="`Move ${goal.title} down`" data-goal-down @click="move(g.goals, i, 1)" />
                </template>
              </div>
            </Card>
          </li>
        </ul>
      </template>
    </section>
    <section v-if="!only && data?.no_area.length" class="flex flex-col gap-2" data-area-section data-area="No area">
      <div class="border-b border-outline-gray-2 pb-2"><h2 class="text-base-medium text-ink-gray-9">No area <span class="text-sm font-normal text-ink-gray-6">{{ data.no_area.length }} goal{{ data.no_area.length === 1 ? '' : 's' }}</span></h2></div>
      <ul class="flex flex-col gap-2"><li v-for="goal in data.no_area" :key="goal.name" data-goal-card :data-goal="goal.name">
        <Card class="relative flex flex-col gap-1 hover:bg-surface-gray-1">
          <RouterLink class="absolute inset-0 rounded-5 focus-visible:focus-ring" :to="`/goals/${goal.name}`" :aria-label="`Open ${goal.title}`" data-goal-open />
          <div class="break-words text-base-medium text-ink-gray-9" data-goal-title>{{ goal.title }}</div><div class="text-sm text-ink-gray-6">{{ goal.progress.label }}</div>
        </Card></li></ul>
    </section>
  </div>
  <NewGoalDialog v-model="newOpen" :area="newArea" @saved="created" @habit="load" />
</template>
<script setup>
// Goals > By area (issue 20): one section for each area that is on, its parts as sub-groups, and a card for each goal with its
// Done when, progress, the cycle's week and score, the next action, the open task count and the goal it serves. The old
// goals list (filters, columns) is still behind /goals with any filter in the address (GoalsPlace).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Progress, Select, TabButtons } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import NewGoalDialog from '@/components/goals/NewGoalDialog.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { dotClass } from '@/lib/lens'
import { short, time, weekday } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { askScope } from '@/lib/ask'

const SHOWS = [{ label: 'This cycle', value: 'cycle' }, { label: 'All open', value: 'open' }, { label: 'Finished', value: 'finished' }]
const SORTS = [{ label: 'My order', value: 'order' }, { label: 'By score', value: 'score' }]
const HINT = {
  cycle: ['No goals in this cycle.', 'Goals in the active 12 Week Year show here under their area. Choose All open to see every goal in progress.'],
  open: ['No goals yet.', 'Your goals will show here under the area of life they belong to, with the next step for each.'],
  finished: ['No finished goals yet.', 'Goals you achieve or close show here, under their area.'],
}
const route = useRoute()
const router = useRouter()
const data = ref(null)
const loaded = ref(false)
const only = ref('')
const newOpen = ref(false)
const newArea = ref('')
const dragged = ref(null)
const show = computed(() => (SHOWS.some((s) => s.value === route.query.show) ? route.query.show : 'cycle'))
const sort = computed(() => (route.query.sort === 'score' ? 'score' : 'order'))
const writable = computed(() => canWrite() && !store.isAgent)
const canDrag = computed(() => writable.value && sort.value === 'order')
const sections = computed(() => data.value?.sections || [])
const lensTop = computed(() => (store.lensArea ? sections.value.find((s) => s.area === store.lensArea || s.parts.some((p) => p.name === store.lensArea))?.area || '' : ''))
const shown = computed(() => sections.value.filter((s) => (only.value || lensTop.value ? s.area === (only.value || lensTop.value) : true)))
const sub = computed(() => {
  if (!data.value) return store.space
  const n = data.value.total
  const areas = sections.value.filter((s) => s.count).length
  return `${n} goal${n === 1 ? '' : 's'} across ${areas} area${areas === 1 ? '' : 's'} of life.`
})

const areaLine = (s) => [`${s.count} goal${s.count === 1 ? '' : 's'}`, ...(s.count ? s.groups.filter((g) => g.area).map((g) => g.area.area_name) : [])].join(' · ')
const doneWhen = (g) => (g.done_when_line ? (g.measure_kind === 'Number' ? `Done when: ${g.measure ? g.measure + ' ' : ''}${g.done_when_line}` : `Done when: ${g.done_when_line}`) : 'No finish line yet')
function nextWhen(n) {
  if (n.scheduled_at) return `${weekday(n.scheduled_at, 3)} ${time(n.scheduled_at)}`
  return n.due_date ? short(n.due_date) : ''
}
const go = (q) => router.push({ query: { ...route.query, ...q } })
const numbers = ref(null)
async function load() {
  const res = await tryCall(() => api('goals.by_area', { space: store.space, show: show.value, sort: sort.value }))
  if (res) data.value = res
  numbers.value = (await tryCall(() => api('counts.get', { space: store.space, which: 'goals', area: store.lensArea || undefined }))) || numbers.value
  loaded.value = true
}
function addGoal(area) {
  newArea.value = area
  newOpen.value = true
}
async function created(g) {
  await load()
  router.push(`/goals/${g.name}`)
}
// the owner's order: move one step, or drag over another card of the same group; saved when dropped
async function save(list) {
  await tryCall(() => api('goals.reorder', { goals: list.map((x) => x.name) }))
}
function move(list, i, by) {
  const j = i + by
  if (j < 0 || j >= list.length) return
  list.splice(j, 0, list.splice(i, 1)[0])
  save(list)
}
function over(list, target) {
  const from = list.findIndex((x) => x.name === dragged.value?.name)
  const to = list.indexOf(target)
  if (from === to || Math.min(from, to) < 0) return
  list.splice(to, 0, list.splice(from, 1)[0])
}
function drop(list) {
  if (dragged.value && list.some((x) => x.name === dragged.value.name)) save(list)
  dragged.value = null
}
watch([show, sort, () => store.space], load)
onMounted(() => { loadLookups(); load() })
askScope({ kind: 'goals', label: 'All goals' })
</script>
