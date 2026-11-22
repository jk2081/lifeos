<template>
  <template v-if="d">
    <PageHead :title="d.title" :crumb="{ to: '/goals', label: 'Goals', here: 'Focus' }" :sub="sub">
      <Button v-if="writable" label="Edit" icon-left="lucide-pencil" data-focus-edit @click="editOpen = true" />
      <Button v-if="canAddGoal" variant="solid" icon-left="lucide-plus" label="Goal for this focus" data-focus-add-goal @click="goalOpen = true" />
    </PageHead>
    <div class="page-body max-w-6xl"><div class="grid items-start gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]" data-focus-page :data-loaded="1">
      <div class="flex min-w-0 flex-col gap-4">
        <Card class="flex flex-col gap-2" data-focus-standard>
          <div class="text-sm text-ink-gray-6">Standard: what good looks like, kept up over time</div>
          <p v-if="d.standard" class="text-lg text-ink-gray-9" data-standard-text>{{ d.standard }}</p>
          <p v-else class="text-base text-ink-gray-6" data-standard-empty>No standard yet. Say what good looks like, in a line or two.
            <Button v-if="writable" size="sm" variant="subtle" label="Write it" @click="editOpen = true" /></p>
        </Card>
        <Card class="flex flex-col gap-2" data-focus-principles>
          <div class="flex flex-wrap items-baseline gap-2">
            <h2 class="text-base-medium text-ink-gray-9">Principles</h2>
            <span class="text-sm text-ink-gray-6">guidelines you and your agents work within</span>
            <Button v-if="writable && !editing" class="ml-auto" size="sm" variant="ghost" label="Edit" data-principles-edit @click="startEdit" />
          </div>
          <ol v-if="!editing" class="flex flex-col">
            <li v-for="(p, i) in d.principles" :key="i" class="flex items-baseline gap-3 border-b border-outline-gray-1 py-2 last:border-b-0" data-principle>
              <span class="w-5 flex-none rounded-4 bg-surface-gray-2 text-center text-xs tabular-nums text-ink-gray-6">{{ i + 1 }}</span>
              <span class="min-w-0 break-words text-base text-ink-gray-9">{{ p }}</span>
            </li>
          </ol>
          <p v-if="!editing && !d.principles.length" class="text-sm text-ink-gray-6" data-principles-empty>No principles yet. Short lines on how to work, in order.</p>
          <div v-if="editing" class="flex flex-col gap-2" data-principles-editor>
            <div v-for="(p, i) in draft" :key="p.id" class="flex items-center gap-2" data-principle-row>
              <span class="w-5 flex-none text-center text-sm tabular-nums text-ink-gray-6">{{ i + 1 }}</span>
              <FormControl class="min-w-0 flex-1" type="text" v-model="p.line" :aria-label="`Principle ${i + 1}`" data-principle-input />
              <Button size="sm" variant="ghost" icon="lucide-arrow-up" label="Move up" :disabled="i === 0" data-principle-up @click="move(i, -1)" />
              <Button size="sm" variant="ghost" icon="lucide-arrow-down" label="Move down" :disabled="i === draft.length - 1" data-principle-down @click="move(i, 1)" />
              <Button size="sm" variant="ghost" icon="lucide-x" label="Remove" data-principle-remove @click="draft.splice(i, 1)" />
            </div>
            <div class="flex flex-wrap gap-2">
              <Button size="sm" icon-left="lucide-plus" label="Add a principle" data-principle-add @click="draft.push({ id: ++seq, line: '' })" />
              <Button class="ml-auto" size="sm" label="Cancel" @click="editing = false" />
              <Button size="sm" variant="solid" label="Save" :loading="busy" data-principles-save @click="savePrinciples" />
            </div>
          </div>
        </Card>
        <Card class="flex flex-col gap-1" data-focus-goals>
          <div class="flex flex-wrap items-baseline gap-2"><h2 class="text-base-medium text-ink-gray-9">Goals serving this focus</h2>
            <span class="text-sm text-ink-gray-6">short goals come and go; the focus stays</span></div>
          <div v-if="!d.has_annual" class="flex flex-wrap items-center gap-2 py-1" data-focus-no-annual>
            <Badge theme="orange" label="No annual goal" />
            <Button v-if="canAddGoal" size="sm" variant="subtle" icon-left="lucide-plus" label="Annual goal" data-focus-annual @click="addAnnual" />
          </div>
          <ul class="flex flex-col">
            <li v-for="r in rows" :key="r.name" class="flex flex-wrap items-center gap-3 border-b border-outline-gray-1 py-2 last:border-b-0" :class="r.finished && 'opacity-60'" data-focus-goal :data-horizon="r.tag">
              <span class="w-28 flex-none rounded-4 bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7" data-goal-tag>{{ r.tag }}</span>
              <RouterLink class="min-w-0 flex-1 break-words text-base text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`/goals/${r.name}`">{{ r.title }}
                <span v-if="r.target_date" class="text-sm text-ink-gray-6">· by {{ short(r.target_date, true) }}</span></RouterLink>
              <span class="text-sm tabular-nums text-ink-gray-7">{{ r.finished ? r.outcome : r.progress.label }}</span>
            </li>
          </ul>
          <p v-if="!rows.length" class="text-sm text-ink-gray-6" data-focus-goals-empty>No goals yet. Add an annual goal to say what this focus is for this year.</p>
        </Card>
      </div>
      <div class="flex min-w-0 flex-col gap-4">
        <Card class="flex flex-col gap-2" data-focus-going>
          <h2 class="text-base-medium text-ink-gray-9">How it is going</h2>
          <ul class="flex flex-col gap-1.5 text-sm text-ink-gray-8">
            <li data-going-cycles>A goal in {{ d.going.cycles_with_goal }} of the last {{ d.going.cycles_considered || 3 }} cycles</li>
            <li data-going-last>{{ d.going.last_activity ? `Last activity: ${d.going.last_activity.title}, ${short(d.going.last_activity.on.slice(0, 10))}` : 'No activity yet' }}</li>
            <li data-going-notes>{{ d.going.notes }} note{{ d.going.notes === 1 ? '' : 's' }} and {{ d.going.captures }} capture{{ d.going.captures === 1 ? '' : 's' }} filed here</li>
          </ul>
        </Card>
        <Card class="flex flex-col gap-1">
          <h2 class="text-base-medium text-ink-gray-9">In the 12-week review</h2>
          <p class="text-sm text-ink-gray-6">Each focus gets one question: set a goal this cycle, or just maintain it.</p>
        </Card>
        <Card class="flex flex-col gap-1">
          <h2 class="text-base-medium text-ink-gray-9">What agents see</h2>
          <p class="text-sm text-ink-gray-6">The standard and principles are part of the core card, so your agents work within them when a task touches {{ d.title }}.</p>
        </Card>
      </div>
    </div></div>
    <NewGoalDialog v-model="goalOpen" :area="d.name" :horizon="goalHorizon" @saved="goalSaved" />
    <Dialog v-model:open="editOpen" title="Edit focus" size="sm" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Save', variant: 'solid', onClick: saveFocus }]">
      <div class="flex flex-col gap-3" data-focus-form>
        <FormControl v-model="form.title" label="Name" data-focus-name />
        <FormControl v-model="form.standard" type="textarea" :rows="3" label="Standard" placeholder="What good looks like, in a line or two" data-focus-standard-input />
        <ErrorMessage v-if="formError" :message="formError" />
      </div>
    </Dialog>
  </template>
  <Card v-else-if="missing" class="m-4 py-2" data-focus-missing><Empty title="This focus is not here.">
    <p class="mt-1">It may be switched off, archived or in a space you cannot open.</p><Button class="mt-3" label="Back to Goals" route="/goals" /></Empty></Card>
</template>
<script setup>
// A focus's own page (issue 57): its standard, numbered principles (edit, reorder), goals by horizon (annual, 12 Week Year, others, then
// finished ones greyed) and how it is going. Principles and the standard are saved through settings.save_item (the owner only).
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dialog, ErrorMessage, FormControl, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import PageHead from '@/components/PageHead.vue'
import NewGoalDialog from '@/components/goals/NewGoalDialog.vue'
import { api, errorText } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'

const props = defineProps({ id: String })
const router = useRouter()
const d = ref(null)
const missing = ref(false)
const editing = ref(false)
const draft = ref([])
const busy = ref(false)
const seq = ref(0)
const goalOpen = ref(false)
const goalHorizon = ref('')
const editOpen = ref(false)
const formError = ref('')
const form = reactive({ title: '', standard: '' })
const writable = computed(() => !!d.value?.writable && !store.isAgent)
const canAddGoal = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write' && !store.isAgent)
const sub = computed(() => ['Focus', d.value.life_area?.area_name, d.value.part?.area_name, 'ongoing, never "done"'].filter(Boolean).join(' · '))
const rows = computed(() => [
  ...d.value.annual.map((g) => ({ ...g, tag: 'Annual' })),
  ...d.value.cycle.map((g) => ({ ...g, tag: '12 Week Year' })),
  ...d.value.other.map((g) => ({ ...g, tag: g.horizon === 'Long term' ? 'Open (to sort)' : g.horizon })),
  ...d.value.finished.map((g) => ({ ...g, tag: `Done · ${g.horizon === '12 weeks' ? '12 weeks' : g.horizon}`, finished: true })),
])
async function load() {
  missing.value = false
  try {
    d.value = await api('focus.get', { area: props.id })
    Object.assign(form, { title: d.value.title, standard: d.value.standard || '' })
  } catch (e) {
    d.value = null
    missing.value = true
  }
}
function startEdit() {
  draft.value = d.value.principles.map((line) => ({ id: ++seq.value, line }))
  editing.value = true
}
function move(i, by) {
  const j = i + by
  if (j < 0 || j >= draft.value.length) return
  draft.value.splice(j, 0, draft.value.splice(i, 1)[0])
}
async function savePrinciples() {
  busy.value = true
  try {
    await api('settings.save_item', { kind: 'area', name: props.id, principles: draft.value.map((p) => p.line).filter((l) => l.trim()) })
    toast.success('Saved')
    editing.value = false
    await load()
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
async function saveFocus({ close }) {
  formError.value = ''
  try {
    await api('settings.save_item', { kind: 'area', name: props.id, title: form.title, standard: form.standard })
    toast.success('Saved')
    close()
    await load()
    loadLookups(true)
  } catch (e) {
    formError.value = errorText(e)
  }
}
function addAnnual() {
  goalHorizon.value = 'Year'
  goalOpen.value = true
}
async function goalSaved(g) {
  await load()
  router.push(`/goals/${g.name}`)
}
watch(() => props.id, load)
watch(goalOpen, (o) => { if (!o) goalHorizon.value = '' })
onMounted(load)
</script>
