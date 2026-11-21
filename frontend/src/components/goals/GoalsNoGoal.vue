<template>
  <PageHead title="Goals" sub="Tasks that serve no goal yet. Each one is still filed in an area, guessed by the Brain.">
    <Button v-if="writable" variant="solid" icon-left="lucide-plus" label="Task" data-new-task @click="openAdd" />
  </PageHead>
  <div class="page-body flex max-w-6xl flex-col gap-4" data-no-goal :data-loaded="loaded ? 1 : 0">
    <Alert theme="blue" title="Every task gets an area, even without a goal." description="The Brain guesses it from what the task is about and who it involves. Change any guess with Area; it learns from that." />
    <Card v-if="adding && writable" class="flex flex-col gap-2" data-no-goal-add>
      <TextInput ref="addInput" v-model="addText" placeholder="Add a task and press Enter. The Brain guesses its area." aria-label="Add a task" @keydown.enter="add" />
    </Card>
    <Card v-if="loaded && data && !data.total" class="py-2" data-no-goal-empty>
      <Empty title="Every open task serves a goal.">
        <p class="mt-1">Tasks with no goal, and the area the Brain guessed for each, will show here so you can attach them to a goal or leave them as they are.</p>
        <TextInput v-if="writable" v-model="emptyText" class="mt-3" placeholder="Add a task and press Enter" aria-label="Add a task" data-no-goal-empty-add @keydown.enter="addEmpty" />
      </Empty>
    </Card>

    <Card v-if="data?.groups?.length" class="flex flex-col gap-1 !p-4 md:!p-5" data-no-goal-card>
      <section v-for="g in data.groups" :key="g.key" class="flex flex-col" data-no-goal-group :data-group="g.label" :data-on="g.is_on ? 1 : 0">
        <div class="flex flex-wrap items-center gap-2 pb-1 pt-3 first:pt-0" :class="g.is_on ? '' : 'opacity-70'">
          <span v-if="g.colour" class="size-2.5 rounded-full" :class="dotClass(g)" aria-hidden="true" />
          <h2 class="text-base-medium text-ink-gray-9">{{ g.label }}</h2>
          <span class="text-sm text-ink-gray-6" data-group-count>{{ g.count }} task{{ g.count === 1 ? '' : 's' }}{{ g.is_on ? '' : ' · area is off' }}</span>
          <RouterLink v-if="!g.is_on" class="ml-auto text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" to="/settings?tab=areas">Switch on {{ g.label }}</RouterLink>
        </div>
        <div v-if="g.suggestion && writable" class="mb-1 flex flex-col gap-2 rounded-md bg-surface-violet-1 px-3 py-2 sm:flex-row sm:items-center sm:justify-between" data-suggestion>
          <span class="text-sm text-ink-violet-8">✦ These {{ g.suggestion.tasks.length }} look like a goal: <strong>{{ g.suggestion.title }}</strong>?</span>
          <Button size="sm" variant="solid" label="Make it a goal" :loading="making === g.key" data-make-goal @click="makeGoal(g)" />
        </div>
        <ul class="flex flex-col">
          <li v-for="t in g.tasks" :key="t.name" class="flex flex-col gap-2 border-b border-outline-gray-1 py-3 last:border-b-0 md:flex-row md:items-center md:gap-4"
            data-no-goal-row :data-task="t.name" :data-guessed="t.area_guessed ? 1 : 0">
            <div class="flex min-w-0 flex-1 items-start gap-2.5">
              <Checkbox class="relative mt-0.5" :model-value="false" :disabled="!writable" :aria-label="`Done: ${t.title}`" @update:model-value="done(t)" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <button type="button" class="break-words text-left text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" data-task-title @click="openRef('task:' + t.name)">{{ t.title }}</button>
                  <span v-if="t.is_top_three" class="text-ink-amber-3" aria-label="Top three">★</span>
                  <AreaGuess :task="t" :readonly="!writable" @confirmed="onConfirmed" />
                </div>
                <div v-if="t.part || t.status === 'Waiting'" class="text-sm text-ink-gray-6">
                  <span v-if="t.part">{{ t.part }}</span><span v-if="t.part && t.status === 'Waiting'"> · </span>
                  <span v-if="t.status === 'Waiting'">Waiting{{ t.waiting_on ? ' on ' + t.waiting_on : '' }}</span>
                </div>
              </div>
            </div>
            <div v-if="writable" class="flex flex-wrap items-center gap-2 pl-7 md:pl-0" data-row-actions>
              <Dropdown :options="areaMenu(t)" align="end">
                <Button size="sm" variant="outline" label="Area" icon-right="lucide-chevron-down" data-area-menu :aria-label="`Area of ${t.title}`" />
              </Dropdown>
              <Button size="sm" variant="outline" label="Fine as is" data-fine-as-is @click="fine(t)" />
              <Dropdown :options="goalMenu(t, g)" align="end">
                <Button size="sm" variant="outline" label="Add to goal" data-add-to-goal :aria-label="`Add ${t.title} to a goal`" />
              </Dropdown>
            </div>
          </li>
        </ul>
      </section>
    </Card>
    <div v-if="data?.truncated" class="text-sm text-ink-gray-6">Showing the first 1,000 tasks.</div>
  </div>
</template>
<script setup>
// Goals > No goal (issue 22): open tasks with no goal, grouped by the area they are filed in (✦ where the Brain guessed it).
// Per task: Area (confirm or move), Fine as is (stays without a goal, leaves this list) and Add to goal (that area's goals first).
// Per group: when three or more tasks share a word, Make it a goal, which creates the goal and attaches them. Nothing happens
// without the click.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Alert, Button, Checkbox, Dropdown, TextInput, toast } from 'frappe-ui'
import AreaGuess from '@/components/AreaGuess.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { dotClass } from '@/lib/lens'
import { areaLabel, loadLookups, lookups } from '@/lib/lookups'
import { onRecordChanged, openRef } from '@/lib/pane'

const emit = defineEmits(['changed'])
const data = ref(null)
const loaded = ref(false)
const making = ref('')
const adding = ref(false)
const addText = ref('')
const emptyText = ref('')
const addInput = ref(null)
const writable = computed(() => canWrite())

async function load() {
  const res = await tryCall(() => api('tasks.no_goal', { space: store.space }))
  if (res) data.value = res
  loaded.value = true
  emit('changed')
}
async function act(fn) {
  try {
    await fn()
    await load()
  } catch (e) {
    toast.error(errorText(e))
  }
}
const areaMenu = (t) => lookups.areas.map((a) => ({ label: areaLabel(a), icon: a.name === t.area ? 'lucide-check' : undefined,
  onClick: () => act(() => api('tasks.confirm_area', { task: t.name, area: a.name })) }))
// goals of the task's area first, then the others (the server's order within each)
function goalMenu(t, g) {
  const goals = data.value?.goals || []
  const own = goals.filter((x) => x.area && x.area === (t.area || g.area))
  const rest = goals.filter((x) => !own.includes(x))
  const item = (x) => ({ label: x.title, onClick: () => act(() => api('tasks.update', { task: t.name, values: { goal: x.name } })) })
  const out = []
  if (own.length) out.push({ group: `Goals in ${g.label}`, options: own.map(item) })
  if (rest.length) out.push({ group: own.length ? 'Other goals' : 'Goals', options: rest.map(item) })
  return out.length ? out : [{ label: 'No goals yet. Make one on By area.', disabled: true }]
}
const fine = (t) => act(() => api('tasks.keep_standalone', { task: t.name }))
const done = (t) => act(() => api('tasks.set_status', { task: t.name, status: 'Done' }))
const onConfirmed = () => load()
async function makeGoal(g) {
  making.value = g.key
  try {
    const res = await api('tasks.make_goal', { tasks: g.suggestion.tasks, space: store.space, area: g.area || undefined })
    toast.success(`Made the goal "${res.title}" with ${res.tasks.length} tasks`)
    await load()
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    making.value = ''
  }
}
async function addTask(text, clear) {
  if (!text || !text.trim()) return
  const res = await tryCall(() => api('tasks.quick_add', { text: text.trim(), space: store.space }))
  if (!res) return
  clear()
  await load()
}
const add = () => addTask(addText.value, () => (addText.value = ''))
const addEmpty = () => addTask(emptyText.value, () => (emptyText.value = ''))
async function openAdd() {
  adding.value = true
  await nextTick()
  addInput.value?.$el?.querySelector('input')?.focus()
}
watch(() => store.space, load)
onRecordChanged(load)
onMounted(() => { loadLookups(); load() })
</script>
