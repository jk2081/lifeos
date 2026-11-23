<template>
  <!-- First run (issue 49): five short screens, each skippable, closable at any point. One screen at a time at every width. -->
  <div class="fixed inset-0 z-50 overflow-y-auto bg-surface-base" role="dialog" aria-modal="true" aria-label="Welcome to Life OS" data-guide :data-step="step.key">
    <div class="mx-auto flex min-h-full w-full max-w-xl flex-col px-5 pb-8 pt-4">
      <div class="flex items-center justify-between gap-3">
        <span class="text-sm text-ink-gray-6" data-guide-count>Step {{ index + 1 }} of {{ STEPS.length }}</span>
        <Button variant="ghost" icon="lucide-x" aria-label="Close the guide" data-guide-close @click="close" />
      </div>
      <div class="mt-2 flex gap-1" aria-hidden="true"><span v-for="(s, i) in STEPS" :key="s.key" class="h-1 flex-1 rounded-full" :class="i <= index ? 'bg-surface-gray-7' : 'bg-surface-gray-3'" /></div>

      <section class="flex flex-1 flex-col gap-4 pt-8" :data-guide-step="step.key">
        <template v-if="step.key === 'welcome'">
          <h1 class="text-2xl font-semibold text-ink-gray-9">Welcome to Life OS</h1>
          <p class="text-base text-ink-gray-7">Everything you capture is filed for you onto your areas and goals, and you only decide what it could not.</p>
          <ol class="flex flex-col gap-2" data-guide-flow>
            <li v-for="(f, i) in FLOW" :key="f.title" class="rounded-5 border p-3" :class="f.brain ? 'border-outline-violet-1 bg-surface-violet-1' : 'border-outline-gray-2'">
              <div class="text-sm text-ink-gray-6">{{ i + 1 }} · {{ f.title }}</div>
              <div class="mt-0.5 text-base text-ink-gray-8">{{ f.text }}</div>
            </li>
          </ol>
        </template>

        <template v-else-if="step.key === 'you'">
          <h1 class="text-2xl font-semibold text-ink-gray-9">You</h1>
          <p class="text-base text-ink-gray-7">How should Life OS call you, and where are you?</p>
          <TextInput v-model="you.name" label="Your name" autocomplete="name" data-guide-name @keydown.enter="next" />
          <label class="flex flex-col gap-1.5 text-sm text-ink-gray-6">Time zone
            <select v-model="you.zone" class="h-7 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-base text-ink-gray-8 focus-visible:focus-ring" data-guide-zone>
              <option v-for="z in zones" :key="z" :value="z">{{ z }}</option>
            </select>
          </label>
          <ErrorMessage v-if="error" :message="error" data-guide-error />
        </template>

        <template v-else-if="step.key === 'areas'">
          <h1 class="text-2xl font-semibold text-ink-gray-9">Your areas</h1>
          <p class="text-base text-ink-gray-7">Seven areas cover a whole life. Career and Health are on. Switch on the others you want.</p>
          <div class="flex flex-col" data-guide-areas>
            <div v-for="a in lifeAreas" :key="a.name" class="flex items-center gap-3 border-b border-outline-gray-1 py-2.5 last:border-b-0" :data-guide-area="a.area_name" :data-on="a.is_on ? 1 : 0">
              <Switch :model-value="!!a.is_on" :disabled="busy === a.name" :aria-label="`${a.area_name} ${a.is_on ? 'on' : 'off'}`" :data-guide-switch="a.area_name"
                @update:model-value="(v) => switchArea(a, v)" />
              <div class="min-w-0 flex-1">
                <div class="text-base-medium text-ink-gray-9">{{ a.area_name }}</div>
                <div class="text-sm text-ink-gray-6">{{ a.description }}</div>
              </div>
            </div>
          </div>
          <div class="rounded-5 border border-outline-gray-2 p-3" data-guide-part>
            <div class="text-base-medium text-ink-gray-9">Add a part</div>
            <p class="mt-0.5 text-sm text-ink-gray-6">For something you run inside an area, such as a business under Career.</p>
            <div class="mt-2 flex flex-col gap-2 sm:flex-row">
              <Select v-model="part.area" class="sm:w-40" :options="onAreas" aria-label="Part of" data-guide-part-area />
              <TextInput v-model="part.title" class="min-w-0 flex-1" placeholder="For example Tea & Coffee" aria-label="Name of the part" data-guide-part-title @keydown.enter="addPart" />
              <Button label="Add" :loading="busy === 'part'" data-guide-part-add @click="addPart" />
            </div>
            <div v-if="parts.length" class="mt-2 flex flex-wrap gap-1.5" data-guide-parts><Badge v-for="p in parts" :key="p.name" size="md" :label="p.label" /></div>
          </div>
          <ErrorMessage v-if="error" :message="error" data-guide-error />
        </template>

        <template v-else-if="step.key === 'things'">
          <h1 class="text-2xl font-semibold text-ink-gray-9">First things</h1>
          <p class="text-base text-ink-gray-7">What is on your mind? Type up to three things. Each becomes a task, filed under the area it seems to belong to. To speak instead, use the microphone on your keyboard.</p>
          <template v-if="!made.length">
            <TextInput v-for="(_, i) in things" :key="i" v-model="things[i]" :placeholder="PLACEHOLDERS[i]" :aria-label="`Thing ${i + 1}`" :data-guide-thing="i" @keydown.enter="next" />
          </template>
          <ul v-else class="flex flex-col gap-2" data-guide-made>
            <li v-for="t in made" :key="t.name" class="flex items-center justify-between gap-3 rounded-5 border border-outline-gray-2 p-3" data-guide-task>
              <span class="min-w-0 break-words text-base text-ink-gray-9">{{ t.title }}</span>
              <Badge size="md" :label="t.area_name || 'No area'" data-guide-task-area />
            </li>
          </ul>
          <ErrorMessage v-if="error" :message="error" data-guide-error />
        </template>

        <template v-else>
          <h1 class="text-2xl font-semibold text-ink-gray-9">You are at level 1</h1>
          <p class="text-base text-ink-gray-7">Life OS works as a task app already. The next step is to let things come to you: connect your email or calendar, and tasks appear on their own.</p>
          <div class="flex flex-col gap-2 pt-2">
            <Button variant="solid" size="lg" label="Connect your email or calendar" data-guide-connect @click="finish('/brain/sources')" />
            <Button size="lg" label="Start using Today" data-guide-today @click="finish('/today')" />
          </div>
        </template>
      </section>

      <div v-if="step.key !== 'next'" class="mt-8 flex items-center justify-between gap-3">
        <Button v-if="index" variant="ghost" label="Back" data-guide-back @click="back" />
        <span v-else />
        <div class="flex items-center gap-2">
          <Button v-if="step.key !== 'welcome'" variant="ghost" label="Skip" data-guide-skip @click="skip" />
          <Button variant="solid" :label="nextLabel" :loading="busy === 'next'" data-guide-next @click="next" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { settingsData } from '@/data/settings'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, ErrorMessage, Select, Switch, TextInput } from 'frappe-ui'
import { errorText } from '@/lib/api'
import { loadLookups } from '@/lib/lookups'
import { finishOnboarding, onboarding } from '@/lib/onboarding'
import { refreshCounts, store } from '@/lib/store'

const router = useRouter()
const STEPS = [{ key: 'welcome' }, { key: 'you' }, { key: 'areas' }, { key: 'things' }, { key: 'next' }]
const FLOW = [
  { title: 'Sources', text: 'Everything that comes in: things you drop in, email, calendar, chats and voice notes.' },
  { title: 'Brain', brain: true, text: 'Reads what comes in, files it, and asks you only about what needs a decision.' },
  { title: 'Plan', text: 'Your goals and tasks, organised by the areas of your life, and the calendar.' },
]
const PLACEHOLDERS = ['Book the dentist', 'Pay the electricity bill', 'Call mum on Sunday']

const index = ref(0)
const step = computed(() => STEPS[index.value])
const error = ref('')
const busy = ref('')
const touched = ref(false) // did the person do anything, or only skip

const you = reactive({ name: onboarding.fullName === 'Administrator' ? '' : onboarding.fullName, zone: onboarding.timeZone || 'UTC' })
const zones = computed(() => {
  const all = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return [...new Set([you.zone, ...all, 'UTC'])].filter(Boolean)
})

const areaRows = ref([])
const lifeAreas = computed(() => areaRows.value.filter((a) => a.is_life_area))
const onAreas = computed(() => lifeAreas.value.filter((a) => a.is_on).map((a) => ({ label: a.area_name, value: a.name })))
const part = reactive({ area: '', title: '' })
const parts = ref([])
async function loadAreas() {
  areaRows.value = (await settingsData.area.tree({ space: store.space, include_off: 1 })).areas
  if (!onAreas.value.some((o) => o.value === part.area)) part.area = onAreas.value[0]?.value || ''
}
async function switchArea(a, on) {
  busy.value = a.name
  error.value = ''
  try {
    await settingsData.settings.save_item({ kind: 'area', space: store.space, name: a.name, is_on: on ? 1 : 0 })
    touched.value = true
    await loadAreas()
  } catch (e) { error.value = errorText(e) } finally { busy.value = '' }
}
async function addPart() {
  if (!part.title.trim() || !part.area) return
  busy.value = 'part'
  error.value = ''
  try {
    const made = await settingsData.settings.save_item({ kind: 'area', space: store.space, title: part.title.trim(), parent_area: part.area })
    parts.value.push({ name: made.name, label: `${part.title.trim()} · ${onAreas.value.find((o) => o.value === part.area)?.label}` })
    part.title = ''
    touched.value = true
    await loadAreas()
  } catch (e) { error.value = errorText(e) } finally { busy.value = '' }
}

const things = ref(['', '', ''])
const made = ref([])

const nextLabel = computed(() => (step.value.key === 'welcome' ? 'Start' : step.value.key === 'things' && made.value.length ? 'Continue' : 'Next'))

function go(to) { error.value = ''; index.value = Math.max(0, Math.min(STEPS.length - 1, to)) }
function back() { go(index.value - 1) }
function skip() { go(index.value + 1) }
async function next() {
  error.value = ''
  const key = step.value.key
  if (key === 'you' && you.name.trim()) {
    busy.value = 'next'
    try {
      const out = await settingsData.onboarding.save_you({ full_name: you.name, time_zone: you.zone })
      store.fullName = out.full_name
      touched.value = true
    } catch (e) { error.value = errorText(e); return } finally { busy.value = '' }
  }
  if (key === 'things' && !made.value.length && things.value.some((t) => t.trim())) {
    busy.value = 'next'
    try {
      made.value = await settingsData.onboarding.add_first_things({ things: things.value.filter((t) => t.trim()), space: store.space })
      touched.value = true
      return // show what was made; Continue goes on
    } catch (e) { error.value = errorText(e); return } finally { busy.value = '' }
  }
  go(index.value + 1)
}

async function finish(to) {
  await finishOnboarding(touched.value ? 'done' : 'skipped')
  await Promise.all([loadLookups(true), refreshCounts()])
  router.push(to)
}
// closing at any point ends the guide; what was done stays
async function close() {
  await finishOnboarding('skipped')
  await Promise.all([loadLookups(true), refreshCounts()])
}

onMounted(loadAreas)
</script>
