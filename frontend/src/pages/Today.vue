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
      <div class="stats">
        <Stat label="To review">
          <NumLink :to="DOOR.review" data-door="today-review" :aria-label="`${d.to_review.count} to review`">{{ d.to_review.count }}</NumLink>
          <template #sub><NumLink class="max-md:hidden" :to="DOOR.review" data-door="today-proposals"><span>{{ d.to_review.proposals }}</span> proposal{{ d.to_review.proposals === 1 ? '' : 's' }} waiting</NumLink></template>
        </Stat>
        <Stat label="Due today">
          <NumLink :to="DOOR.due" data-door="today-due" :aria-label="`${d.tasks.due} due today or overdue`">{{ d.tasks.due }}</NumLink>
          <template #sub><NumLink class="max-md:hidden" :to="DOOR.overdue" data-door="today-overdue"><span>{{ d.tasks.overdue }}</span> overdue</NumLink></template>
        </Stat>
        <Stat class="max-md:hidden" :label="d.cycle && d.cycle.week ? `Week ${d.cycle.week} score` : 'Week score'" :sub="`Target ${d.target}%`">
          <NumLink :to="DOOR.score" data-door="today-score">{{ d.cycle && d.cycle.week ? Math.round(d.cycle.score) + '%' : '—' }}</NumLink>
        </Stat>
        <Stat label="Open loops">
          <NumLink :to="DOOR.loops" data-door="today-loops" :aria-label="`${d.open_loops} open loops`">{{ d.open_loops }}</NumLink>
          <template #sub><span class="max-md:hidden">Older than 14 days, no date</span></template>
        </Stat>
      </div>

      <div class="cols">
        <div class="wide">
          <section v-if="d.habits.length" class="md:hidden">
            <SectionHead>Habits today</SectionHead>
            <HabitBoxes :habits="d.habits" bare @toggle="toggleHabit" />
          </section>
          <section>
            <SectionHead>Tasks</SectionHead>
            <Card flush>
              <TaskRow v-for="t in d.tasks.items" :key="t.name" :task="t" :today="d.date" :readonly="!canWrite()" @toggle="done" />
              <Empty v-if="!d.tasks.items.length" title="Nothing is due today." hint="Tasks due today or overdue show here. Press n to add one." />
            </Card>
          </section>
          <section>
            <SectionHead>To review</SectionHead>
            <Card flush>
              <Row v-for="it in d.to_review.items" :key="it.name" :pane="'inbox:' + it.name" :label="it.title">
                <div class="min-w-0 flex-1">
                  <div class="break-words text-base-medium text-ink-gray-9">{{ it.title }}</div>
                  <div class="text-sm text-ink-gray-6"><span class="max-md:hidden">{{ it.state }} · </span><NumLink class="relative" data-door="today-row"
                    :to="{ query: { ...$route.query, open: 'inbox:' + it.name, focus: 'pending' } }">{{ it.pending }} of {{ it.proposals }} proposals pending</NumLink><span
                    v-if="it.processed_by" class="max-md:hidden"> · filed by {{ it.processed_by }}, {{ time(it.received_on) }}</span></div>
                </div>
                <Badge theme="amber"><span class="max-md:hidden">To review</span><span class="md:hidden">Review</span></Badge>
              </Row>
              <Empty v-if="!d.to_review.items.length" title="Nothing to review." hint="Drop a file in the Inbox. What the agent proposes waits here for you." />
            </Card>
          </section>
        </div>

        <div class="side">
          <section class="max-md:hidden">
            <SectionHead>Habits today</SectionHead>
            <HabitBoxes v-if="d.habits.length" :habits="d.habits" @toggle="toggleHabit" />
            <Card v-else><Empty title="No habits this month." hint="Add habits in Journal, Habits, Manage habits." /></Card>
          </section>
          <section>
            <SectionHead>Calendar</SectionHead>
            <Card flush>
              <Row v-for="e in d.events" :key="e.name + e.start" :pane="'event:' + e.name" :label="e.title">
                <span class="w-14 shrink-0 tabular-nums text-ink-gray-7">{{ e.date !== d.date ? weekday(e.date, 3) : e.all_day ? 'All day' : time(e.start) }}</span>
                <div class="min-w-0 flex-1 break-words text-ink-gray-8">{{ e.title }}</div>
              </Row>
              <Empty v-if="!d.events.length" title="Nothing on the calendar today." hint="Events from the calendar show here." />
            </Card>
          </section>
          <section>
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
  </template>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button } from 'frappe-ui'
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
import { long, time, weekday } from '@/lib/dates'
import { onRecordChanged, paneNav } from '@/lib/pane'

const d = ref(null)
const phone = useMediaQuery('(max-width: 767px)') // the header shows a three-letter weekday on a phone
// each number on Today leads to the list it counts
const DOOR = { review: { path: '/inbox', query: { status: 'To Review' } }, due: { path: '/tasks', query: { view: 'list', due: 'today,overdue' } },
  overdue: { path: '/tasks', query: { view: 'list', due: 'overdue' } }, loops: { path: '/tasks', query: { status: 'loops' } }, vault: { path: '/vault', query: { expiry: 'soon' } },
  score: { path: '/journal', query: { all: '1' } } }
const comingRef = (c) => (c.kind === 'vault' ? 'vault:' : 'date:') + c.name

async function load() {
  const res = await tryCall(() => api('today.get', { space: store.space }))
  if (!res) return
  d.value = res
  paneNav.rows = [...res.tasks.items.map((t) => 'task:' + t.name), ...res.to_review.items.map((i) => 'inbox:' + i.name),
    ...res.events.map((e) => 'event:' + e.name), ...res.coming_up.map(comingRef)]
}
onRecordChanged(load)
async function done(t) {
  await optimistic(() => { t.status = 'Done'; t._done = true }, () => { t.status = 'Open'; t._done = false },
    () => api('tasks.set_status', { task: t.name, status: 'Done' })).catch(() => {})
  setTimeout(load, 600)
}
function toggleHabit(h) {
  optimistic(() => (h.done = !h.done), () => (h.done = !h.done),
    () => api('journal.toggle_habit', { habit: h.habit, date: d.value.date, done: h.done ? 1 : 0 })).catch(() => {})
}
onMounted(load)
onUnmounted(() => (paneNav.rows = []))
</script>
