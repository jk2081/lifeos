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
        <RouterLink class="bt p" to="/inbox" style="color: var(--surface-base)">Add to Inbox</RouterLink>
      </div>
      <button class="bt s ic only-phone" type="button" aria-label="Search" @click="store.searchOpen = true"><Ico :d="SEARCH_ICON" :size="20" /></button>
    </header>

    <div class="bd">
      <div class="stats">
        <div class="cd st"><span class="mt">To review</span>
          <RouterLink class="big" :to="DOOR.review" data-door="today-review" :aria-label="`${d.to_review.count} to review`"><b>{{ d.to_review.count }}</b></RouterLink>
          <RouterLink class="mt only-desktop" :to="DOOR.review" data-door="today-proposals"><span>{{ d.to_review.proposals }}</span> proposal{{ d.to_review.proposals === 1 ? '' : 's' }} waiting</RouterLink></div>
        <div class="cd st"><span class="mt">Due today</span>
          <RouterLink class="big" :to="DOOR.due" data-door="today-due" :aria-label="`${d.tasks.due} due today or overdue`"><b>{{ d.tasks.due }}</b></RouterLink>
          <RouterLink class="mt only-desktop" :to="DOOR.overdue" data-door="today-overdue"><span>{{ d.tasks.overdue }}</span> overdue</RouterLink></div>
        <div class="cd st hide-phone"><span class="mt">{{ d.cycle && d.cycle.week ? `Week ${d.cycle.week} score` : 'Week score' }}</span>
          <RouterLink class="big" to="/journal" data-door="today-score"><b>{{ d.cycle && d.cycle.week ? Math.round(d.cycle.score) + '%' : '—' }}</b></RouterLink><span class="mt">Target {{ d.target }}%</span></div>
        <div class="cd st"><span class="mt">Open loops</span>
          <RouterLink class="big" :to="DOOR.loops" data-door="today-loops" :aria-label="`${d.open_loops} open loops`"><b>{{ d.open_loops }}</b></RouterLink>
          <span class="mt only-desktop">Older than 14 days, no date</span></div>
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
              <TaskRow v-for="t in d.tasks.items" :key="t.name" :task="t" :today="d.date" :readonly="!canWrite()" @toggle="done" @open="openRef('task:' + t.name)" />
              <Empty v-if="!d.tasks.items.length" title="Nothing is due today." hint="Tasks due today or overdue show here. Press n to add one." />
            </div>
          </section>
          <section>
            <h2 class="sh">To review</h2>
            <div class="cd list">
              <div v-for="it in d.to_review.items" :key="it.name" class="rw rowlink" :class="{ on: isOpen('inbox:' + it.name) }" :data-ref="'inbox:' + it.name" tabindex="0"
                @click="(e) => !e.target.closest('a') && openRef('inbox:' + it.name)" @keydown.enter.self="openRef('inbox:' + it.name)">
                <div class="grow">
                  <div class="ttl">{{ it.title }}</div>
                  <div class="mt"><span class="only-desktop">{{ it.state }} · </span><a href="#" class="num" data-door="today-row"
                    @click.prevent="openRef('inbox:' + it.name, { focus: 'pending' })">{{ it.pending }} of {{ it.proposals }} proposals pending</a><span
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
              <div v-for="e in d.events" :key="e.name + e.start" class="rw rowlink" :class="{ on: isOpen('event:' + e.name) }" :data-ref="'event:' + e.name" tabindex="0"
                @click="openRef('event:' + e.name)" @keydown.enter.self="openRef('event:' + e.name)">
                <span class="when">{{ e.date !== d.date ? weekday(e.date, 3) : e.all_day ? 'All day' : time(e.start) }}</span><div>{{ e.title }}</div>
              </div>
              <Empty v-if="!d.events.length" title="Nothing on the calendar today." hint="Events from the calendar show here." />
            </div>
          </section>
          <section>
            <h2 class="sh">Coming up <RouterLink v-if="d.vault_soon" class="more num" :to="DOOR.vault" data-door="today-vault"><span>{{ d.vault_soon }}</span> document{{ d.vault_soon === 1 ? '' : 's' }} expiring within 60 days</RouterLink></h2>
            <div class="cd list">
              <div v-for="c in d.coming_up" :key="c.kind + c.name" class="rw rowlink" :class="{ on: isOpen(comingRef(c)) }" :data-ref="comingRef(c)" tabindex="0"
                @click="openRef(comingRef(c))" @keydown.enter.self="openRef(comingRef(c))">
                <div class="grow"><div class="ttl">{{ c.title }}</div>
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
  </template>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import Ico from '@/components/Ico.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import HabitBoxes from '@/components/HabitBoxes.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long, time, weekday } from '@/lib/dates'
import { SEARCH_ICON } from '@/lib/nav'
import { current, onRecordChanged, openRef, paneNav } from '@/lib/pane'

const d = ref(null)
// each number on Today leads to the list it counts
const DOOR = { review: { path: '/inbox', query: { status: 'To Review' } }, due: { path: '/tasks', query: { view: 'list', due: 'today,overdue' } },
  overdue: { path: '/tasks', query: { view: 'list', due: 'overdue' } }, loops: { path: '/tasks', query: { view: 'loops' } }, vault: { path: '/vault', query: { expiry: 'soon' } } }
const isOpen = (ref_) => current.value?.ref === ref_
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
<style scoped>
.st a { color: inherit; text-decoration: none; }
.st a.big:hover b, .st a.mt:hover { color: var(--ink-blue-8); text-decoration: underline; }
.when { width: 52px; flex: none; font-variant-numeric: tabular-nums; color: var(--ink-gray-7); }
</style>
