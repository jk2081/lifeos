<template>
  <!-- First run (issues 49, 97): six short screens in one frame. Title, one line, the content, then the footer straight under it: Back on the left,
       Skip (optional steps that start empty) and the primary button on the right. One screen at a time at every width. -->
  <div v-show="!onboarding.away" class="fixed inset-0 z-50 overflow-y-auto bg-surface-base" role="dialog" aria-modal="true" aria-label="Welcome to Life OS" data-guide :data-step="step.key">
    <div class="mx-auto w-full max-w-xl px-5 pb-8 pt-4">
      <div class="flex items-center justify-between gap-3">
        <span class="text-sm text-ink-gray-6" data-guide-count>Step {{ index + 1 }} of {{ STEPS.length }}</span>
        <Button variant="ghost" icon="lucide-x" aria-label="Close the guide" data-guide-close @click="close" />
      </div>
      <div class="mt-2 flex gap-1" aria-hidden="true"><span v-for="(s, i) in STEPS" :key="s.key" class="h-1 flex-1 rounded-full" :class="i <= index ? 'bg-surface-gray-7' : 'bg-surface-gray-3'" /></div>

      <section class="flex flex-col gap-4 pt-8" :data-guide-step="step.key">
        <h1 class="text-2xl font-semibold text-ink-gray-9" data-guide-title>{{ step.title }}</h1>
        <p class="text-base text-ink-gray-7" data-guide-line>{{ step.line }}</p>

        <template v-if="step.key === 'welcome'">
          <ol class="flex flex-col gap-2" data-guide-flow>
            <li v-for="(f, i) in FLOW" :key="f.title" class="rounded-5 border border-outline-gray-2 p-3" data-guide-card>
              <div class="text-sm text-ink-gray-6">{{ i + 1 }} · {{ f.title }}</div>
              <div class="mt-0.5 text-base text-ink-gray-8">{{ f.text }}</div>
            </li>
          </ol>
        </template>

        <template v-else-if="step.key === 'you'">
          <TextInput v-model="you.name" label="What should we call you?" autocomplete="nickname" data-guide-name @keydown.enter="next" />
          <Select v-model="you.zone" label="Time zone" :options="zones" data-guide-zone />
        </template>

        <template v-else-if="step.key === 'areas'">
          <div class="flex flex-col" data-guide-areas>
            <Row bare v-for="a in lifeAreas" :key="a.name" class="py-3" :data-guide-area="a.area_name" :data-on="a.is_on ? 1 : 0">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="text-base-medium text-ink-gray-9">{{ a.area_name }}</div>
                  <div class="text-sm text-ink-gray-6">{{ a.description }}</div>
                </div>
                <Switch :model-value="!!a.is_on" :disabled="busy === a.name" :aria-label="`${a.area_name} ${a.is_on ? 'on' : 'off'}`" :data-guide-switch="a.area_name"
                  @update:model-value="(v) => switchArea(a, v)" />
              </div>
              <ul v-if="partsOf(a).length" class="ml-4 mt-2 flex flex-col gap-1" data-guide-parts>
                <li v-for="p in partsOf(a)" :key="p.name" class="flex items-center justify-between gap-2" :class="a.is_on ? 'text-ink-gray-8' : 'text-ink-gray-6'" data-guide-part :data-kept="a.is_on ? 0 : 1">
                  <span class="min-w-0 break-words text-base">{{ p.area_name }}</span>
                  <Badge v-if="!a.is_on" label="Kept" />
                  <Button v-else variant="ghost" size="sm" icon="lucide-x" :aria-label="`Remove ${p.area_name}`" :disabled="busy === p.name" data-guide-part-remove @click="removePart(p)" />
                </li>
              </ul>
              <div v-if="a.is_on" class="ml-4 mt-1">
                <div v-if="adding === a.name" class="flex items-center gap-2">
                  <TextInput v-model="partTitle" class="min-w-0 flex-1" placeholder="For example Tea & Coffee" :aria-label="`Name of the part of ${a.area_name}`" data-guide-part-title @keydown.enter="addPart(a)" />
                  <Button label="Add" :loading="busy === 'part'" data-guide-part-add @click="addPart(a)" />
                  <Button variant="ghost" icon="lucide-x" aria-label="Cancel" @click="adding = ''" />
                </div>
                <Button v-else variant="ghost" size="sm" icon-left="lucide-plus" label="Add a part" :data-guide-add-part="a.area_name" @click="startPart(a)" />
              </div>
            </Row>
          </div>
        </template>

        <template v-else-if="step.key === 'brain'">
          <div v-if="onboarding.aiSet" class="flex items-center gap-2 rounded-5 border border-outline-gray-2 p-3 text-base text-ink-gray-9" data-guide-brain-on>
            <span class="lucide-check size-4 text-ink-green-7" aria-hidden="true" /> The Brain is on
          </div>
          <template v-else>
            <TextInput v-model="aiKey" type="password" label="AI key" autocomplete="off" data-guide-key @keydown.enter="next" />
            <a class="w-fit text-sm text-ink-blue-8 hover:underline focus-visible:focus-ring" href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener" data-guide-key-help>Where do I get a key?</a>
          </template>
        </template>

        <template v-else-if="step.key === 'things'">
          <div class="flex flex-col gap-2" data-guide-rows>
            <template v-for="(r, i) in rows" :key="r.id">
              <Row bare v-if="r.task" class="flex flex-wrap items-center gap-2 pb-2" data-guide-task>
                <span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ r.task.title }}</span>
                <Dropdown :options="areaMenu(r)">
                  <Button size="sm" :variant="r.state === 'sure' ? 'subtle' : 'outline'" :label="areaLabel(r)" :loading="r.state === 'filing'" icon-right="lucide-chevron-down" :disabled="r.state === 'filing'" data-guide-task-area />
                </Dropdown>
                <Button variant="ghost" size="sm" icon="lucide-x" :aria-label="`Remove ${r.task.title}`" data-guide-task-remove @click="removeTask(r)" />
              </Row>
              <TextInput v-else v-model="r.text" :aria-label="`Thing ${i + 1}`" :data-guide-thing="i" @keydown.enter="next" />
            </template>
          </div>
          <p v-if="phone" class="text-sm text-ink-gray-6" data-guide-mic>To speak instead, use the microphone on your keyboard.</p>
        </template>

        <template v-else>
          <p class="text-base text-ink-gray-9" data-guide-summary>{{ summary }}</p>
          <p v-if="!onboarding.aiSet" class="text-sm text-ink-gray-6" data-guide-brain-off>The Brain is off: add an AI key in Settings › AI.</p>
          <p class="text-base text-ink-gray-7">Connect Google or Microsoft, and your mail and calendar start coming in on their own.</p>
          <Button class="w-fit" :icon-left="onboarding.googleConnected ? 'lucide-check' : undefined" :disabled="onboarding.googleConnected"
            :label="onboarding.googleConnected ? 'Google is connected' : 'Connect Google or Microsoft'" data-guide-connect @click="connect" />
        </template>

        <ErrorMessage v-if="error" :message="error" data-guide-error />
      </section>

      <div class="mt-6 flex items-center justify-between gap-3" data-guide-footer>
        <Button v-if="index" label="Back" data-guide-back @click="back" />
        <span v-else />
        <div class="flex items-center gap-2">
          <Button v-if="skippable" variant="ghost" label="Skip" data-guide-skip @click="skip" />
          <Button variant="solid" :label="nextLabel" :loading="busy === 'next'" data-guide-next @click="next" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Row from '@/components/ui/Row.vue'
import { settingsData } from '@/data/settings'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dropdown, ErrorMessage, Select, Switch, TextInput } from 'frappe-ui'
import { errorText } from '@/lib/api'
import { loadLookups } from '@/lib/lookups'
import { STEP_KEY, finishOnboarding, loadOnboarding, onboarding } from '@/lib/onboarding'
import { refreshCounts, store } from '@/lib/store'
import { currentZone, zoneLabel } from '@/lib/timezones'
import { plural } from '@/lib/plural'

const router = useRouter()
const STEPS = [
  { key: 'welcome', title: 'Welcome to Life OS', line: "Everything you capture is filed onto your areas and goals. You decide only what it can't." },
  { key: 'you', title: 'You', line: 'What should Life OS call you, and where are you?' },
  { key: 'areas', title: 'Your areas', line: 'Seven areas cover a whole life. Switch on the ones you want; you can change them later.' },
  { key: 'brain', title: 'Turn on the Brain', line: 'An AI key lets Life OS file things into the right area, answer questions in Chat, and write your daily summary. It stays encrypted on your server.' },
  { key: 'things', title: "What's on your mind?", line: 'Up to three things. Each becomes a task in the right area. For example: pay the electricity bill.' },
  { key: 'done', title: "You're set up", line: '' },
]
const FLOW = [
  { title: 'Sources', text: 'Everything that comes in: things you drop in, email, calendar, chats and voice notes.' },
  { title: 'Brain', text: 'Reads what comes in, files it, and asks you only about what needs a decision.' },
  { title: 'Plan', text: 'Your goals and tasks, organised by the areas of your life, and the calendar.' },
]
const MAX_THINGS = 3
const WAIT_MS = 5000 // how long the guide waits for the model's guess before saying "Not sure"

const saved = (() => { try { return JSON.parse(sessionStorage.getItem(STEP_KEY) || '{}') } catch (e) { return {} } })()
const index = ref(Math.min(Number(saved.step) || 0, STEPS.length - 1))
const step = computed(() => STEPS[index.value])
const error = ref('')
const busy = ref('')
const touched = ref(false) // did the person do anything, or only skip
const tasksMade = ref(Number(saved.tasks) || 0)
watch([index, tasksMade], () => sessionStorage.setItem(STEP_KEY, JSON.stringify({ step: index.value, tasks: tasksMade.value })))

// phones show the keyboard-microphone hint; a computer does not
const query = window.matchMedia('(max-width: 799px)')
const phone = ref(query.matches)
const onQuery = () => { phone.value = query.matches }
query.addEventListener('change', onQuery)
onBeforeUnmount(() => query.removeEventListener('change', onQuery))

const you = reactive({ name: onboarding.callMe || '', zone: detectedZone() })
function detectedZone() {
  const seen = currentZone(Intl.DateTimeFormat().resolvedOptions().timeZone)
  const all = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone').map(currentZone) : []
  return seen && (all.includes(seen) || seen === onboarding.timeZone) ? seen : onboarding.timeZone || 'UTC'
}
const zones = computed(() => {
  const all = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return [...new Set([you.zone, ...all.map(currentZone), 'UTC'])].filter(Boolean).map((z) => ({ label: zoneLabel(z), value: z }))
})

const areaRows = ref([])
const lifeAreas = computed(() => areaRows.value.filter((a) => a.is_life_area))
const partsOf = (a) => areaRows.value.filter((p) => p.parent_area === a.name)
const adding = ref('')
const partTitle = ref('')
async function loadAreas() {
  areaRows.value = (await settingsData.area.tree({ space: store.space, include_off: 1 })).areas
}
async function guarded(key, fn) {
  busy.value = key
  error.value = ''
  try { await fn(); touched.value = true } catch (e) { error.value = errorText(e) } finally { busy.value = '' }
}
const switchArea = (a, on) => guarded(a.name, async () => {
  await settingsData.settings.save_item({ kind: 'area', space: store.space, name: a.name, is_on: on ? 1 : 0 })
  if (!on && adding.value === a.name) adding.value = ''
  await loadAreas()
})
function startPart(a) { adding.value = a.name; partTitle.value = '' }
const addPart = (a) => partTitle.value.trim() && guarded('part', async () => {
  await settingsData.settings.save_item({ kind: 'area', space: store.space, title: partTitle.value.trim(), parent_area: a.name })
  partTitle.value = ''
  adding.value = ''
  await loadAreas()
})
const removePart = (p) => guarded(p.name, async () => {
  await settingsData.settings.save_item({ kind: 'area', space: store.space, name: p.name, is_archived: 1 })
  await loadAreas()
})

// the first things: three boxes, then each as a task with the area it was filed under
let seq = 0
const draft = () => ({ id: ++seq, text: '', task: null })
const rows = ref(Array.from({ length: MAX_THINGS }, draft))
const onAreas = computed(() => lifeAreas.value.filter((a) => a.is_on))
function areaLabel(r) {
  if (r.state === 'filing') return 'Filing…'
  if (r.state === 'unsure') return 'Not sure'
  if (r.state === 'off') return `${r.areaName} (off)`
  return r.areaName
}
function areaMenu(r) {
  const items = onAreas.value.map((a) => ({ label: a.area_name, onClick: () => pick(r, a) }))
  if (r.state === 'off') items.unshift({ label: `Switch on ${r.areaName}`, icon: 'lucide-power', onClick: () => pick(r, lifeAreas.value.find((a) => a.name === r.area), true) })
  return items
}
const pick = (r, a, switchOn = false) => guarded(`row${r.id}`, async () => {
  if (switchOn) { await settingsData.settings.save_item({ kind: 'area', space: store.space, name: a.name, is_on: 1 }); await loadAreas() }
  await settingsData.tasks.update({ task: r.task.name, values: { area: a.name } })
  Object.assign(r, { area: a.name, areaName: a.area_name, state: 'sure' })
})
const removeTask = (r) => guarded(`row${r.id}`, async () => {
  await settingsData.onboarding.remove_first_thing({ task: r.task.name })
  rows.value = rows.value.filter((x) => x !== r)
  tasksMade.value = Math.max(0, tasksMade.value - 1)
  if (rows.value.length < MAX_THINGS && !rows.value.some((x) => !x.task)) rows.value.push(draft())
})
function withTimeout(promise, ms) {
  return Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(null), ms))])
}
// ask the model for each filed row at once; whatever has not answered in WAIT_MS stays "Not sure"
async function fileRows(made) {
  await Promise.all(made.map(async (r) => {
    const late = settingsData.onboarding.guess_area({ task: r.task.name }).catch(() => null)
    const got = await withTimeout(late, WAIT_MS)
    if (got) apply(r, got)
    else { if (r.state === 'filing') r.state = 'unsure'; late.then((g) => g && r.state === 'unsure' && apply(r, g)) }
  }))
}
function apply(r, got) {
  Object.assign(r, { area: got.area, areaName: got.area_name, state: got.is_on ? 'sure' : 'off' })
}

const lastStep = computed(() => index.value === STEPS.length - 1)
const skippable = computed(() => (step.value.key === 'brain' && !onboarding.aiSet) || step.value.key === 'things')
const nextLabel = computed(() => (step.value.key === 'welcome' ? 'Start' : lastStep.value ? 'Done' : 'Next'))
const summary = computed(() => {
  const on = onAreas.value.length
  const parts = onAreas.value.reduce((n, a) => n + partsOf(a).length, 0)
  return [plural(on, 'area'), plural(parts, 'part'), plural(tasksMade.value, 'task')].join(', ')
})

function go(to) { error.value = ''; index.value = Math.max(0, Math.min(STEPS.length - 1, to)) }
function back() { go(index.value - 1) }
function skip() { go(index.value + 1) }
async function next() {
  error.value = ''
  const key = step.value.key
  if (key === 'you' && you.name.trim()) {
    busy.value = 'next'
    try {
      await settingsData.onboarding.save_you({ call_me: you.name, time_zone: you.zone })
      touched.value = true
    } catch (e) { error.value = errorText(e); return } finally { busy.value = '' }
  }
  if (key === 'brain' && aiKey.value.trim()) {
    busy.value = 'next'
    try {
      await settingsData.onboarding.save_ai_key({ key: aiKey.value })
      aiKey.value = ''
      onboarding.aiSet = true
      touched.value = true
    } catch (e) { error.value = errorText(e); return } finally { busy.value = '' }
  }
  if (key === 'things') {
    const fresh = rows.value.filter((r) => !r.task && r.text.trim())
    if (fresh.length) {
      busy.value = 'next'
      try {
        const made = await settingsData.onboarding.add_first_things({ things: fresh.map((r) => r.text), space: store.space })
        const filed = fresh.map((r, i) => {
          const t = made[i]
          return Object.assign(r, { task: t, area: t.area, areaName: t.area_name, state: t.unsure ? (onboarding.aiSet ? 'filing' : 'unsure') : 'sure' })
        })
        tasksMade.value += filed.length
        rows.value = rows.value.filter((r) => r.task || r.text.trim())
        if (rows.value.length < MAX_THINGS) rows.value.push(draft())
        touched.value = true
        fileRows(filed.filter((r) => r.state === 'filing'))
        return // show what was made and where; Next goes on
      } catch (e) { error.value = errorText(e); return } finally { busy.value = '' }
    }
  }
  if (lastStep.value) return finish('/today')
  go(index.value + 1)
}
const aiKey = ref('')

// to Connections and back: the guide stays where it is, hidden, and App shows "Back to the guide"
function connect() {
  onboarding.away = true
  router.push('/brain/sources')
}
watch(() => onboarding.away, (away) => { if (!away) loadOnboarding() })

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
