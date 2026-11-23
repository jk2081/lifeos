<template>
  <PageHead title="Goals" :sub="sub">
    <Button variant="subtle" label="Reset" route="/settings?tab=data" data-all-tasks-reset />
    <Button v-if="writable" variant="solid" icon-left="lucide-plus" label="Task" data-new-task @click="openTopAdd" />
  </PageHead>
  <div class="page-body flex max-w-6xl flex-col gap-4" data-all-tasks :data-loaded="loaded ? 1 : 0">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2" data-task-controls>
      <TextInput v-model="search" class="w-full sm:w-56" type="search" placeholder="Search tasks" aria-label="Search tasks" data-task-search />
      <nav class="flex flex-wrap items-center gap-2" aria-label="Show" data-task-shows>
        <Button v-for="s in shows" :key="s.value" :variant="show === s.value ? 'solid' : 'subtle'" :label="`${s.label} ${data?.counts?.[s.value] ?? ''}`.trim()"
          :data-task-show="s.value" @click="go({ show: s.value === 'open' ? undefined : s.value })" />
      </nav>
      <div class="flex items-center gap-2" role="group" aria-label="Group by" data-task-group>
        <span class="text-sm text-ink-gray-6">Group by</span>
        <Button v-for="g in GROUPS" :key="g.value" :variant="group === g.value ? 'solid' : 'subtle'" :label="g.label" :data-task-group-by="g.value"
          @click="go({ group: g.value === 'area' ? undefined : g.value })" />
      </div>
    </div>
    <nav class="flex flex-wrap items-center gap-2" aria-label="Areas" data-task-areas>
      <Button :variant="only ? 'subtle' : 'solid'" label="Every area" data-task-area-chip="all" @click="only = ''" />
      <Button v-for="a in data?.areas || []" :key="a.name" :variant="only === a.name ? 'solid' : 'subtle'" :label="a.area_name" :data-task-area-chip="a.area_name" @click="only = a.name">
        <template #prefix><span class="size-2 rounded-full" :class="dotClass(a)" aria-hidden="true" /></template>
      </Button>
    </nav>

    <Card v-if="topAdd && writable" class="flex flex-col gap-2" data-task-top-add>
      <TextInput ref="topInput" v-model="topText" placeholder="Add a task and press Enter. A date word such as tomorrow or fri sets the due date. The Brain guesses its area." aria-label="Add a task"
        @keydown.enter="add({}, topText, () => (topText = ''))" />
    </Card>
    <Card v-if="loaded && data && !data.total" class="py-2" data-tasks-empty>
      <Empty :title="HINT[show][0]">
        <p class="mt-1">{{ HINT[show][1] }}</p>
        <TextInput v-if="writable && show === 'open'" v-model="emptyText" class="mt-3" placeholder="Add a task and press Enter" aria-label="Add your first task"
          data-tasks-empty-add @keydown.enter="add({}, emptyText, () => (emptyText = ''))" />
      </Empty>
    </Card>

    <section v-for="g in data?.groups || []" :key="g.key" class="flex flex-col gap-1" data-task-group-section :data-group="g.label">
      <div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 pb-2">
        <span v-if="g.colour" class="size-2.5 rounded-full" :class="dotClass(g)" aria-hidden="true" />
        <h2 class="text-base-medium text-ink-gray-9">{{ g.label }}</h2>
        <span class="text-sm text-ink-gray-6" data-group-count>{{ g.count }}</span>
      </div>
      <TextInput v-if="canAdd(g)" v-model="texts[g.key]" class="my-1" size="sm" :placeholder="`Add a task to ${g.label}`" :aria-label="`Add a task to ${g.label}`"
        :data-group-add="g.label" @keydown.enter="add(addArgs(g), texts[g.key], () => (texts[g.key] = ''))" />
      <template v-for="p in g.parts" :key="p.name">
        <h3 v-if="p.label" class="mt-1 text-sm-medium text-ink-gray-7" data-part-head>{{ p.label }}</h3>
        <ul class="flex flex-col">
          <li v-for="t in p.tasks" :key="t.name" class="flex flex-col gap-1 border-b border-outline-gray-1 py-2 last:border-b-0 md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,14rem)_6rem] md:items-center md:gap-4"
            data-task-row :data-task="t.name" :data-guessed="t.area_guessed ? 1 : 0">
            <div class="flex min-w-0 items-start gap-2.5">
              <Checkbox class="relative mt-0.5" :model-value="t.status === 'Done'" :disabled="!writable" :aria-label="`Done: ${t.title}`" @update:model-value="toggle(t)" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <button type="button" class="break-words text-left text-base-medium hover:underline focus-visible:focus-ring" :class="t.status === 'Done' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'"
                    data-task-title @click="openRef('task:' + t.name)">{{ t.title }}</button>
                  <span v-if="t.is_top_three" class="text-ink-amber-3" title="One of your top three" aria-label="Top three" data-top-three>★</span>
                  <AreaGuess :task="t" :readonly="!writable" />
                </div>
                <div v-if="t.status === 'Waiting' || (group !== 'area' && t.area_name && !t.area_guessed)" class="text-sm text-ink-gray-6">
                  <span v-if="t.status === 'Waiting'">Waiting{{ t.waiting_on ? ' on ' + t.waiting_on : '' }}</span><span v-if="t.status === 'Waiting' && group !== 'area' && t.area_name && !t.area_guessed"> · </span>
                  <span v-if="group !== 'area' && t.area_name && !t.area_guessed">{{ t.area_name }}</span>
                </div>
              </div>
            </div>
            <div class="min-w-0 pl-7 text-sm md:pl-0" data-task-goal>
              <span v-if="t.goal_title" class="inline-flex max-w-full items-center gap-1.5 text-ink-gray-7"><span class="size-2 shrink-0 rounded-full bg-surface-gray-5" aria-hidden="true" /><span class="truncate">{{ t.goal_title }}</span></span>
              <Badge v-else theme="orange" label="No goal" />
            </div>
            <div class="pl-7 text-sm tabular-nums md:pl-0 md:text-right" :class="overdue(t) ? 'text-ink-red-8' : 'text-ink-gray-6'" data-task-due>{{ dueText(t) }}</div>
          </li>
        </ul>
      </template>
    </section>
    <div v-if="data?.truncated" class="text-sm text-ink-gray-6" data-tasks-truncated>Showing the first 1,000 tasks. Narrow by area or search to see the rest.</div>
  </div>
</template>
<script setup>
// Goals > All tasks (issue 21): every open task once, grouped by area (then part), goal or due date, each with its goal or
// "No goal", due date, the top-three star and ✦ when the Brain guessed its area. A quick add at the top of each group files the
// new task in that group's area (and goal). Someday, Waiting, Due and Done are filters here. The old list is behind any
// address that names a filter of its own (GoalsPlace).
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Checkbox, TextInput, toast } from 'frappe-ui'
import AreaGuess from '@/components/AreaGuess.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { dotClass } from '@/lib/lens'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { onRecordChanged, openRef } from '@/lib/pane'

const SHOWS = [{ label: 'All open', value: 'open' }, { label: 'Due', value: 'due' }, { label: 'Waiting on someone', value: 'waiting' },
  { label: 'Someday', value: 'someday' }, { label: 'Done', value: 'done' }]
// the old Open band's "untouched 30+ days" (issue 55) is a filter here, after Due
const shows = computed(() => [...SHOWS.slice(0, 2), { label: `Untouched ${data.value?.stuck_days || 30}+ days`, value: 'stuck' }, ...SHOWS.slice(2)])
const GROUPS = [{ label: 'Area', value: 'area' }, { label: 'Goal', value: 'goal' }, { label: 'Due date', value: 'due' }]
const HINT = {
  open: ['No open tasks.', 'Tasks you add, and tasks the Brain finds in what you capture, will show here under the area of life they belong to.'],
  due: ['Nothing is due this week.', 'Open tasks that are overdue or due by the end of this week show here.'],
  stuck: ['Nothing has been left untouched.', 'Open tasks nobody has touched for a month show here, ready for Reset.'],
  waiting: ['Nothing is waiting on someone.', 'A task you are waiting on someone for shows here, with who.'],
  someday: ['Nothing is parked on Someday.', 'Tasks you park for later show here, and come back for review after a while.'],
  done: ['No done tasks yet.', 'Tasks you tick off show here, newest first.'],
}
const route = useRoute()
const router = useRouter()
const data = ref(null)
const loaded = ref(false)
const only = ref('')
const search = ref(route.query.q || '')
const texts = reactive({})
const topAdd = ref(false)
const topText = ref('')
const emptyText = ref('')
const topInput = ref(null)
const show = computed(() => ([...SHOWS, { value: 'stuck' }].some((s) => s.value === route.query.show) ? route.query.show : 'open'))
const group = computed(() => (GROUPS.some((g) => g.value === route.query.group) ? route.query.group : 'area'))
const writable = computed(() => canWrite())
const area = computed(() => only.value || store.lensArea || '')
const sub = computed(() => {
  if (!data.value) return store.space
  const n = data.value.counts.open
  const areas = new Set((data.value.groups || []).map((g) => g.area).filter(Boolean)).size
  return `${n} open task${n === 1 ? '' : 's'}${group.value === 'area' ? ` across ${areas} area${areas === 1 ? '' : 's'}` : ''}.`
})

const overdue = (t) => t.due_date && t.due_date < data.value.today && !['Done', 'Dropped'].includes(t.status)
function dueText(t) {
  if (t.status === 'Done') return t.completed_on ? short(t.completed_on) : 'Done'
  if (!t.due_date) return ''
  if (t.due_date === data.value.today) return 'Today'
  return short(t.due_date)
}
// quick add: a group gives its area and goal; the Today group gives today's date
const canAdd = (g) => writable.value && show.value === 'open' && g.key !== 'done'
const addArgs = (g) => (group.value === 'goal' ? { goal: g.goal || undefined, area: g.area || undefined } : group.value === 'due'
  ? { due_date: g.key === 'today' ? data.value.today : undefined } : { area: g.area || undefined })
async function add(args, text, clear) {
  if (!text || !text.trim()) return
  const res = await tryCall(() => api('tasks.quick_add', { text: text.trim(), space: store.space, ...args }))
  if (!res) return
  clear()
  await load()
}
async function toggle(t) {
  try {
    await api('tasks.set_status', { task: t.name, status: t.status === 'Done' ? 'Open' : 'Done' })
    await load()
  } catch (e) {
    toast.error(errorText(e))
  }
}
async function openTopAdd() {
  topAdd.value = true
  await nextTick()
  topInput.value?.$el?.querySelector('input')?.focus()
}
const go = (q) => router.push({ query: { ...route.query, ...q } })
async function load() {
  const res = await tryCall(() => api('tasks.all_tasks', { space: store.space, group: group.value, show: show.value, area: area.value || undefined, q: search.value || undefined }))
  if (res) data.value = res
  loaded.value = true
}
let timer
watch(search, () => { clearTimeout(timer); timer = setTimeout(load, 250) })
watch([show, group, area, () => store.space], load)
onRecordChanged(load)
onMounted(() => { loadLookups(); load() })
</script>
