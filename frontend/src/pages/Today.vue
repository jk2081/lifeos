<template>
  <template v-if="d">
    <PageHead :title="`${weekday(d.date, phone ? 3 : 0)}, ${long(d.date)}`">
      <template #sub>
        <template v-if="d.cycle && d.cycle.week">Week {{ d.cycle.week }} of {{ d.cycle.weeks }}
          <span class="max-md:hidden"> · {{ d.cycle.title }}</span><span class="md:hidden"> · score {{ Math.round(d.cycle.score) }}%</span></template>
        <template v-else-if="d.cycle">{{ d.cycle.title }} {{ d.cycle.ended ? 'has ended' : 'has not started' }}</template>
        <template v-else>No active 12 Week Year</template>
      </template>
      <Button class="max-md:hidden" label="New task" @click="store.quickAdd = true" />
      <Button class="max-md:hidden" variant="solid" label="Add to Inbox" route="/inbox" />
      <Button class="md:hidden" icon="lucide-search" label="Search" @click="store.searchOpen = true" />
    </PageHead>

    <div class="page-body">
      <div class="stats stats-row">
        <Stat label="To review" compact>
          <NumLink :to="DOOR.review" data-door="today-review" :aria-label="`${d.to_review.count} to review`">{{ d.to_review.count }}</NumLink>
          <template #sub><NumLink :to="DOOR.review" data-door="today-proposals"><span>{{ d.to_review.proposals }}</span> proposal{{ d.to_review.proposals === 1 ? '' : 's' }} waiting</NumLink></template>
        </Stat>
        <Stat label="Due today" compact>
          <NumLink :to="DOOR.due" data-door="today-due" :aria-label="`${d.tasks.due} due today or overdue`">{{ d.tasks.due }}</NumLink>
          <template #sub><NumLink :to="DOOR.overdue" data-door="today-overdue"><span>{{ d.tasks.overdue }}</span> overdue</NumLink></template>
        </Stat>
        <Stat class="max-md:hidden" :label="d.cycle && d.cycle.week ? `Week ${d.cycle.week} score` : 'Week score'">
          <NumLink :to="DOOR.score" data-door="today-score">{{ d.cycle && d.cycle.week ? Math.round(d.cycle.score) + '%' : '—' }}</NumLink>
          <template #sub>
            <div v-if="d.cycle && d.cycle.week" class="mt-1.5" data-score-bar>
              <div class="relative h-1.5 rounded-full bg-surface-gray-3" role="img" :aria-label="`${Math.round(d.cycle.score)}% of the ${d.target}% target`">
                <div class="h-full rounded-full" :class="d.cycle.score >= d.target ? 'bg-surface-green-7' : 'bg-surface-gray-7'" :style="{ width: Math.min(d.cycle.score, 100) + '%' }" />
                <div class="absolute -top-1 h-3.5 w-0.5 rounded-full bg-surface-gray-9" :style="{ left: `calc(${d.target}% - 1px)` }" aria-hidden="true" />
              </div>
              <div class="mt-1.5">{{ d.cycle.done }} of {{ d.cycle.planned }} ticks · target {{ d.target }}%</div>
            </div>
            <template v-else>Target {{ d.target }}%</template>
          </template>
        </Stat>
        <Stat label="Open loops" compact>
          <NumLink :to="DOOR.loops" data-door="today-loops" :aria-label="`${d.open_loops} open loops`">{{ d.open_loops }}</NumLink>
          <template #sub>Older than 14 days, no date</template>
        </Stat>
      </div>

      <!-- on a phone the two columns become one, in this order: habits, to review, tasks, this week, calendar, coming up -->
      <div class="cols today-cols">
        <div class="wide">
          <section class="max-md:order-3" data-today-tasks>
            <SectionHead>Tasks</SectionHead>
            <Card flush>
              <template v-if="d.tasks.today.length || d.tasks.overdue_items.length">
                <div class="group-head">
                  <span>Due today</span><NumLink :to="DOOR.today" data-door="today-group-today">{{ d.tasks.today_count }}</NumLink>
                </div>
                <div v-if="!d.tasks.today.length" class="pb-2.5 text-base text-ink-gray-6">Nothing is due today.</div>
                <TaskRow v-for="t in d.tasks.today" :key="t.name" :task="t" :today="d.date" :readonly="!canWrite()" @toggle="done" />
                <MoreLink v-if="d.tasks.today_count > d.tasks.today.length" :to="DOOR.today" :n="d.tasks.today_count" />

                <template v-if="d.tasks.overdue_items.length">
                  <div class="group-head border-t border-outline-gray-1">
                    <span>Overdue</span><NumLink :to="DOOR.overdue" data-door="today-group-overdue">{{ d.tasks.overdue }}</NumLink>
                    <Button v-if="canWrite()" class="ml-auto" variant="ghost" size="sm" label="Move all to today" data-move-all @click="moveAllOpen = true" />
                  </div>
                  <div v-if="overdueFolded" class="flex items-center gap-3 border-b border-outline-gray-1 py-2.5 last:border-b-0" data-overdue-summary>
                    <span class="min-w-0 flex-1 text-base text-ink-gray-7"><template v-if="oldestDays">The oldest is {{ oldestDays }} day{{ oldestDays === 1 ? '' : 's' }} late.</template> Show them to move or drop one at a time.</span>
                    <Button size="sm" label="Show" icon-right="lucide-chevron-down" data-overdue-show @click="showOverdue = true" />
                  </div>
                  <template v-else>
                    <TaskRow v-for="t in d.tasks.overdue_items" :key="t.name" class="group" :task="t" :today="d.date" :readonly="!canWrite()" @toggle="done">
                      <template v-if="canWrite()" #end>
                        <Dropdown :options="triage(t)"><Button class="relative md:opacity-0 md:focus-visible:opacity-100 md:group-hover:opacity-100" variant="ghost" size="sm"
                          icon="lucide-calendar-clock" :label="'Reschedule ' + t.title" data-triage /></Dropdown>
                      </template>
                    </TaskRow>
                    <MoreLink v-if="d.tasks.overdue > d.tasks.overdue_items.length" :to="DOOR.overdue" :n="d.tasks.overdue" />
                  </template>
                </template>
              </template>
              <Empty v-else title="Nothing is due today." hint="Tasks due today or overdue show here. Press n to add one." />
            </Card>
          </section>
          <section class="max-md:order-2" data-today-review>
            <SectionHead>To review
              <template v-if="d.to_review.count > reviewRows.length" #action><NumLink :to="DOOR.review" data-door="today-review-all">All {{ d.to_review.count }} in Inbox</NumLink></template>
            </SectionHead>
            <Card flush>
              <Row v-for="it in reviewRows" :key="it.name" :pane="'inbox:' + it.name" :label="it.title">
                <div class="min-w-0 flex-1">
                  <div class="break-words text-base-medium text-ink-gray-9">{{ it.title }}</div>
                  <div class="text-sm text-ink-gray-6"><span class="max-md:hidden">{{ it.state }} · </span><NumLink class="relative" data-door="today-row"
                    :to="{ query: { ...$route.query, open: 'inbox:' + it.name, focus: 'pending' } }">{{ it.pending }} of {{ it.proposals }} proposals pending</NumLink><span
                    v-if="it.processed_by" class="max-md:hidden"> · filed by {{ it.processed_by }}, {{ time(it.received_on) }}</span></div>
                </div>
                <Badge theme="amber"><span class="max-md:hidden">To review</span><span class="md:hidden">Review</span></Badge>
              </Row>
              <Empty v-if="!reviewRows.length" title="Nothing to review." hint="Drop a file in the Inbox. What the agent proposes waits here for you." />
            </Card>
          </section>
        </div>

        <div class="side">
          <section class="max-md:order-1" data-today-habits>
            <SectionHead>Habits today
              <template v-if="d.habits.length" #action><span class="font-normal tabular-nums text-ink-gray-6" data-habit-count>{{ habitsDone === d.habits.length ? 'All done' : `${habitsDone} of ${d.habits.length}` }}</span></template>
            </SectionHead>
            <HabitBoxes v-if="d.habits.length" variant="pill" bare :habits="d.habits" @toggle="toggleHabit" />
            <Card v-else><Empty title="No habits this month." hint="Add habits in Journal, Habits, Manage habits." /></Card>
          </section>
          <section v-if="d.cycle && d.cycle.week" class="max-md:order-4" data-today-week>
            <SectionHead>This week · Week {{ d.cycle.week }}
              <template #action><NumLink to="/journal">Open grid</NumLink></template>
            </SectionHead>
            <Card flush>
              <div v-for="a in weekRows" :key="a.name" :data-action="a.name" class="flex items-center gap-3 border-b border-outline-gray-1 py-2 last:border-b-0" data-week-action>
                <div class="min-w-0 flex-1">
                  <div class="break-words text-base" :class="a.count >= a.per_week ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ a.title }}</div>
                  <div class="truncate text-sm text-ink-gray-6">{{ a.goal_title }}</div>
                </div>
                <Button class="!size-10 shrink-0 !p-0 tabular-nums" :variant="a.count >= a.per_week ? 'solid' : a.count ? 'subtle' : 'outline'" :theme="a.count ? 'blue' : 'gray'"
                  :disabled="!canWrite()" :aria-pressed="a.count >= a.per_week" :aria-label="`${a.title}, ${a.count} of ${a.per_week} this week`" data-week-tick @click="tick(a)">
                  <span v-if="a.per_week === 1 && a.count" class="lucide-check size-4" aria-hidden="true" />
                  <span v-else-if="a.per_week > 1" class="text-sm">{{ a.count }}/{{ a.per_week }}</span>
                </Button>
              </div>
              <button v-if="weekRows.length < d.cycle.actions.length" type="button" class="flex items-center gap-1 py-2.5 text-sm-medium text-ink-gray-7 hover:text-ink-gray-9"
                data-week-more @click="showWeek = true">Show all {{ d.cycle.actions.length }}<span class="lucide-chevron-down size-4" aria-hidden="true" /></button>
              <Empty v-if="!d.cycle.actions.length" title="No actions planned this week." hint="Add goals and their weekly actions in Journal, 12 Week Year." />
            </Card>
          </section>
          <section class="max-md:order-5">
            <SectionHead>Calendar</SectionHead>
            <Card flush>
              <Row v-for="e in d.events" :key="e.name + e.start" :pane="'event:' + e.name" :label="e.title">
                <span class="w-14 shrink-0 tabular-nums text-ink-gray-7">{{ e.date !== d.date ? weekday(e.date, 3) : e.all_day ? 'All day' : time(e.start) }}</span>
                <div class="min-w-0 flex-1 break-words text-ink-gray-8">{{ e.title }}</div>
              </Row>
              <Empty v-if="!d.events.length" title="Nothing on the calendar today." hint="Events from the calendar show here." />
            </Card>
          </section>
          <section class="max-md:order-6">
            <SectionHead>Coming up
              <template v-if="d.vault_soon" #action><NumLink :to="DOOR.vault" data-door="today-vault"><span>{{ d.vault_soon }}</span> document{{ d.vault_soon === 1 ? '' : 's' }} expiring within 60 days</NumLink></template>
            </SectionHead>
            <Card flush>
              <Row v-for="c in d.coming_up" :key="c.kind + c.name" :pane="comingRef(c)" :label="c.title">
                <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div>
                  <div v-if="c.kind === 'vault'" class="text-sm text-ink-gray-6">Vault · {{ c.days < 0 ? `expired ${-c.days} days ago` : c.days === 0 ? 'expires today' : `expires in ${c.days} days` }}</div>
                  <div v-else class="text-sm text-ink-gray-6">Important date · {{ long(c.date) }}</div></div>
                <Badge v-if="c.kind === 'vault'" :theme="c.days < 0 ? 'red' : 'amber'" :label="c.days < 0 ? 'Expired' : 'Renew'" />
                <Badge v-else :label="c.days === 0 ? 'Today' : `${c.days} day${c.days === 1 ? '' : 's'}`" />
              </Row>
              <Empty v-if="!d.coming_up.length" title="Nothing coming up." hint="Expiring documents and important dates in the next two weeks show here." />
            </Card>
          </section>
        </div>
      </div>
    </div>

    <Dialog v-model:open="moveAllOpen" title="Move overdue tasks to today?" size="md"
      :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Move to today', variant: 'solid', onClick: moveAll }]">
      <p class="text-base text-ink-gray-8">Every open overdue task in this space gets today as its due date. Their old due dates are not kept.</p>
    </Dialog>
  </template>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button, Dialog, Dropdown, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Stat from '@/components/ui/Stat.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import HabitBoxes from '@/components/HabitBoxes.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { addDays, diffDays, long, startOfWeek, time, weekday } from '@/lib/dates'
import { onRecordChanged, paneNav } from '@/lib/pane'

const d = ref(null)
const phone = useMediaQuery('(max-width: 767px)') // the header shows a three-letter weekday on a phone
// each number on Today leads to the list it counts
const DOOR = { review: { path: '/inbox', query: { status: 'To Review' } }, due: { path: '/tasks', query: { view: 'list', due: 'today,overdue' } },
  today: { path: '/tasks', query: { view: 'list', due: 'today' } },
  overdue: { path: '/tasks', query: { view: 'list', due: 'overdue' } }, loops: { path: '/tasks', query: { status: 'loops' } }, vault: { path: '/vault', query: { expiry: 'soon' } },
  score: { path: '/journal', query: { all: '1' } } }
const comingRef = (c) => (c.kind === 'vault' ? 'vault:' : 'date:') + c.name
const REVIEW_ROWS = 3
const OVERDUE_FOLD = 3 // more overdue rows than this fold into one line until Show is pressed

// the last line of a capped group: "Show all N", leading to the same list as the group's count
const MoreLink = defineComponent({
  props: { to: Object, n: Number },
  setup: (p) => () => h(RouterLink, { to: p.to, class: 'flex items-center gap-1 py-2.5 text-sm-medium text-ink-gray-7 hover:text-ink-gray-9', 'data-show-all': '' },
    () => [`Show all ${p.n}`, h('span', { class: 'lucide-arrow-right size-4', 'aria-hidden': 'true' })]),
})

const reviewRows = computed(() => d.value.to_review.items.slice(0, REVIEW_ROWS))
const showOverdue = ref(false)
const overdueFolded = computed(() => !showOverdue.value && d.value.tasks.overdue_items.length > OVERDUE_FOLD)
const oldestDays = computed(() => d.value.tasks.oldest_overdue ? diffDays(d.value.date, d.value.tasks.oldest_overdue) : 0)
const habitsDone = computed(() => d.value.habits.filter((x) => x.done).length)
const moveAllOpen = ref(false)
// this week's actions, at most WEEK_ROWS until Show all. The ones still to do come first, sorted once on load so a
// row does not jump away when it is ticked.
const WEEK_ROWS = 6
const showWeek = ref(false)
const weekRows = computed(() => (showWeek.value ? d.value.cycle.actions : d.value.cycle.actions.slice(0, WEEK_ROWS)))

async function load() {
  const res = await tryCall(() => api('today.get', { space: store.space }))
  if (!res) return
  if (res.cycle?.actions) {
    const left = (a) => a.count < a.per_week
    res.cycle.actions = [...res.cycle.actions.filter(left), ...res.cycle.actions.filter((a) => !left(a))]
  }
  d.value = res
  paneNav.rows = [...res.tasks.today.map((t) => 'task:' + t.name), ...res.tasks.overdue_items.map((t) => 'task:' + t.name),
    ...res.to_review.items.slice(0, REVIEW_ROWS).map((i) => 'inbox:' + i.name), ...res.events.map((e) => 'event:' + e.name), ...res.coming_up.map(comingRef)]
}
onRecordChanged(load)
async function done(t) {
  await optimistic(() => { t.status = 'Done'; t._done = true }, () => { t.status = 'Open'; t._done = false },
    () => api('tasks.set_status', { task: t.name, status: 'Done' })).catch(() => {})
  setTimeout(load, 600)
}

// an overdue task gets a new date or is dropped; it leaves the overdue group at once
function triage(t) {
  const list = d.value.tasks.overdue_items
  const leave = (request, message) => async () => {
    const at = list.indexOf(t)
    await optimistic(() => list.splice(at, 1), () => list.splice(at, 0, t), request).then(() => toast.success(message)).catch(() => {})
    load()
  }
  const move = (label, date) => ({ label, onClick: leave(() => api('tasks.update', { task: t.name, values: { due_date: date } }), `Moved to ${long(date)}`) })
  return [
    move('Today', d.value.date),
    move('Tomorrow', addDays(d.value.date, 1)),
    move('Next week', addDays(startOfWeek(d.value.date), 7)),
    { label: 'Drop', onClick: leave(() => api('tasks.set_status', { task: t.name, status: 'Dropped' }), 'Dropped') },
  ]
}
async function moveAll({ close }) {
  const out = await tryCall(() => api('tasks.reschedule_overdue', { space: store.space, to_date: d.value.date }))
  close()
  if (!out) return
  toast.success(`${out.moved} task${out.moved === 1 ? '' : 's'} moved to today`)
  showOverdue.value = false
  load()
}

// a tap on this week's action: once a week toggles, more than once counts up and wraps to zero, as on the grid
async function tick(a) {
  const c = d.value.cycle
  const before = a.count
  const next = before >= a.per_week ? 0 : before + 1
  try {
    await optimistic(() => (a.count = next), () => (a.count = before), async () => {
      const score = await api('journal.tick', { action: a.name, week: c.week, count: next })
      Object.assign(c, { done: score.done, planned: score.planned, score: score.percent })
    })
  } catch { /* told by optimistic */ }
}
function toggleHabit(x) {
  optimistic(() => (x.done = !x.done), () => (x.done = !x.done),
    () => api('journal.toggle_habit', { habit: x.habit, date: d.value.date, done: x.done ? 1 : 0 })).catch(() => {})
}
onMounted(load)
onUnmounted(() => (paneNav.rows = []))
</script>
