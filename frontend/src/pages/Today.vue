<template>
  <template v-if="d">
    <header class="hd">
      <div>
        <h1 class="h1"><span class="only-desktop">{{ weekday(d.date) }}, {{ long(d.date) }}</span><span class="only-phone">{{ weekday(d.date, 3) }}, {{ long(d.date) }}</span></h1>
        <div class="sub">
          <template v-if="d.cycle && d.cycle.week">Week {{ d.cycle.week }} of {{ d.cycle.weeks }}
            <span class="only-desktop"> · {{ d.cycle.title }}</span><span class="only-phone"> · score {{ Math.round(d.cycle.score) }}%</span></template>
          <template v-else-if="d.cycle">{{ d.cycle.title }} {{ d.cycle.ended ? 'has ended' : 'has not started' }}</template>
          <template v-else>No active 12 Week Year</template>
        </div>
      </div>
      <div class="only-desktop" style="display: flex; gap: 8px">
        <button class="bt s" type="button" @click="store.quickAdd = true">New task</button>
        <RouterLink class="bt p" to="/inbox" style="color: var(--bg)">Add to Inbox</RouterLink>
      </div>
      <button class="bt s ic only-phone" type="button" aria-label="Search" @click="store.searchOpen = true"><Ico :d="SEARCH_ICON" :size="20" /></button>
    </header>

    <div class="bd">
      <div class="stats">
        <RouterLink to="/inbox" class="cd st"><span class="mt">To review</span><b>{{ d.to_review.count }}</b>
          <span class="mt only-desktop">{{ d.to_review.proposals }} proposal{{ d.to_review.proposals === 1 ? '' : 's' }} waiting</span></RouterLink>
        <RouterLink to="/tasks" class="cd st"><span class="mt">Due today</span><b>{{ d.tasks.due }}</b>
          <span class="mt only-desktop">{{ d.tasks.overdue }} overdue</span></RouterLink>
        <RouterLink to="/journal" class="cd st hide-phone"><span class="mt">{{ d.cycle && d.cycle.week ? `Week ${d.cycle.week} score` : 'Week score' }}</span>
          <b>{{ d.cycle && d.cycle.week ? Math.round(d.cycle.score) + '%' : '—' }}</b><span class="mt">Target {{ d.target }}%</span></RouterLink>
        <RouterLink to="/tasks?view=loops" class="cd st"><span class="mt">Open loops</span><b>{{ d.open_loops }}</b>
          <span class="mt only-desktop">Older than 14 days, no date</span></RouterLink>
      </div>

      <div class="cols">
        <div class="wide">
          <section class="only-phone" v-if="d.habits.length">
            <h2 class="sh">Habits today</h2>
            <HabitBoxes :habits="d.habits" bare @toggle="toggleHabit" />
          </section>
          <section>
            <h2 class="sh">Tasks</h2>
            <div class="cd list">
              <TaskRow v-for="t in d.tasks.items" :key="t.name" :task="t" :today="d.date" :readonly="!canWrite()" @toggle="done" @open="openTask = t.name" />
              <Empty v-if="!d.tasks.items.length" title="Nothing is due today." hint="Tasks due today or overdue show here. Press n to add one." />
            </div>
          </section>
          <section>
            <h2 class="sh">To review</h2>
            <div class="cd list">
              <div v-for="it in d.to_review.items" :key="it.name" class="rw">
                <div class="grow">
                  <RouterLink class="ttl" :to="`/inbox/${it.name}`">{{ it.title }}</RouterLink>
                  <div class="mt"><span class="only-desktop">{{ it.state }} · </span>{{ it.proposals }} proposal{{ it.proposals === 1 ? '' : 's' }}<span
                    class="only-desktop" v-if="it.processed_by"> · filed by {{ it.processed_by }}, {{ time(it.received_on) }}</span></div>
                </div>
                <span class="pl o"><span class="only-desktop">To review</span><span class="only-phone">Review</span></span>
              </div>
              <Empty v-if="!d.to_review.items.length" title="Nothing to review." hint="Drop a file in the Inbox. What the agent proposes waits here for you." />
            </div>
          </section>
        </div>

        <div class="side">
          <section class="only-desktop">
            <h2 class="sh">Habits today</h2>
            <HabitBoxes v-if="d.habits.length" :habits="d.habits" @toggle="toggleHabit" />
            <div v-else class="cd"><Empty title="No habits this month." hint="Add habits in Journal, Habits, Manage habits." /></div>
          </section>
          <section>
            <h2 class="sh">Calendar</h2>
            <div class="cd list">
              <div v-for="e in d.events" :key="e.name + e.start" class="rw">
                <span class="when">{{ e.date !== d.date ? weekday(e.date, 3) : e.all_day ? 'All day' : time(e.start) }}</span><div>{{ e.title }}</div>
              </div>
              <Empty v-if="!d.events.length" title="Nothing on the calendar today." hint="Events from the calendar show here." />
            </div>
          </section>
          <section>
            <h2 class="sh">Coming up</h2>
            <div class="cd list">
              <div v-for="c in d.coming_up" :key="c.kind + c.name" class="rw">
                <div class="grow"><RouterLink class="ttl" style="color: var(--ink)" :to="c.kind === 'vault' ? `/vault?open=${c.name}` : '/calendar/year'">{{ c.title }}</RouterLink>
                  <div class="mt" v-if="c.kind === 'vault'">Vault · {{ c.days < 0 ? `expired ${-c.days} days ago` : c.days === 0 ? 'expires today' : `expires in ${c.days} days` }}</div>
                  <div class="mt" v-else>Important date · {{ long(c.date) }}</div></div>
                <span v-if="c.kind === 'vault'" class="pl" :class="c.days < 0 ? 'r' : 'o'">{{ c.days < 0 ? 'Expired' : 'Renew' }}</span>
                <span v-else class="pl n">{{ c.days === 0 ? 'Today' : `${c.days} day${c.days === 1 ? '' : 's'}` }}</span>
              </div>
              <Empty v-if="!d.coming_up.length" title="Nothing coming up." hint="Expiring documents and important dates in the next two weeks show here." />
            </div>
          </section>
        </div>
      </div>
    </div>
    <TaskPanel v-if="openTask" :name="openTask" @close="openTask = null" @changed="load" />
  </template>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import Ico from '@/components/Ico.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import TaskPanel from '@/components/TaskPanel.vue'
import HabitBoxes from '@/components/HabitBoxes.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long, time, weekday } from '@/lib/dates'
import { SEARCH_ICON } from '@/lib/nav'

const d = ref(null)
const openTask = ref(null)

async function load() {
  const res = await tryCall(() => api('today.get', { space: store.space }))
  if (res) d.value = res
}
async function done(t) {
  await optimistic(() => { t.status = 'Done'; t._done = true }, () => { t.status = 'Open'; t._done = false },
    () => api('tasks.set_status', { task: t.name, status: 'Done' })).catch(() => {})
  setTimeout(load, 600)
}
function toggleHabit(h) {
  optimistic(() => (h.done = !h.done), () => (h.done = !h.done),
    () => api('journal.toggle_habit', { habit: h.habit, date: d.value.date, done: h.done ? 1 : 0 })).catch(() => {})
}
onMounted(() => {
  load()
  window.addEventListener('lifeos-task-added', load)
})
onUnmounted(() => window.removeEventListener('lifeos-task-added', load))
</script>
<style scoped>
a.cd.st { color: inherit; text-decoration: none; }
a.cd.st:hover { background: var(--soft); }
.when { width: 52px; flex: none; font-variant-numeric: tabular-nums; color: var(--mut2); }
</style>
