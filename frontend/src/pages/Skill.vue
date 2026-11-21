<template>
  <PageHead :title="d?.title || 'Skill'" :sub="d ? `${d.trigger} · version ${d.version}` : ''">
    <Button label="All skills" icon-left="lucide-arrow-left" @click="router.push('/brain/skills')" />
    <Switch v-if="d" :model-value="d.active" :disabled="!d.can_edit" :label="d.active ? 'On' : 'Off'" data-skill-active @update:model-value="toggle" />
  </PageHead>
  <div v-if="d" class="page-body flex max-w-4xl flex-col gap-6" data-skill-page :data-skill="d.name" :data-version="d.version">
    <p class="text-sm text-ink-gray-6">{{ d.when_to_use }}</p>

    <Card v-if="d.update_text" class="flex flex-col gap-2" data-skill-update-card>
      <div class="text-base-medium text-ink-gray-9">An update to this built-in skill is available (version {{ d.update_version }} of the app's text)</div>
      <p class="text-sm text-ink-gray-6">Your edit is kept until you take it. The difference, yours on the left:</p>
      <DiffView :before="d.instructions" :after="d.update_text" />
      <div v-if="d.can_edit"><Button label="Take the update" data-take-update @click="takeUpdate" /></div>
    </Card>

    <section class="flex flex-col gap-2" data-skill-instructions>
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-base-medium text-ink-gray-9">Instructions</h2>
        <div class="flex items-center gap-2">
          <Button size="sm" :label="preview ? 'Edit' : 'Preview'" data-skill-preview-toggle @click="preview = !preview" />
          <Button v-if="d.can_edit" size="sm" label="Test" icon-left="lucide-flask-conical" :loading="testing" data-skill-test @click="runTest" />
          <Button v-if="d.can_edit" size="sm" variant="solid" label="Save" :disabled="!dirty" data-skill-save @click="save" />
        </div>
      </div>
      <Md v-if="preview" class="rounded-5 border border-outline-gray-2 p-4" :text="text" data-skill-preview />
      <FormControl v-else v-model="text" type="textarea" :rows="16" :disabled="!d.can_edit" aria-label="Instructions" data-skill-text />
      <p v-if="dirty" class="text-sm text-ink-amber-9">Not saved yet. Test runs the examples against this text; Save makes it version {{ d.version + 1 }}.</p>
    </section>

    <section class="flex flex-col gap-2" data-skill-examples>
      <h2 class="text-base-medium text-ink-gray-9">Examples <span class="text-sm font-normal text-ink-gray-6">Each is a sample capture and what it must make of it.</span></h2>
      <Card v-if="d.examples.length" flush>
        <div v-for="e in d.examples" :key="e.name" class="flex flex-col gap-1 border-b border-outline-gray-1 py-3 last:border-0" data-skill-example>
          <div class="flex items-center gap-2">
            <span class="flex-1 text-base text-ink-gray-9">{{ e.title }}</span>
            <Badge v-if="shown(e)" :theme="shown(e).passed ? 'green' : 'red'" :label="shown(e).passed ? 'Pass' : 'Fail'" :data-example-result="shown(e).passed ? 'pass' : 'fail'" />
            <Badge v-else-if="e.last_result" theme="gray" :label="`Last: ${e.last_result}`" />
          </div>
          <p v-if="shown(e)?.error" class="text-sm text-ink-red-8">{{ shown(e).error }}</p>
          <ul v-if="shown(e)?.checks?.length" class="text-sm text-ink-gray-6">
            <li v-for="(c, i) in shown(e).checks" :key="i" :class="c.passed ? '' : 'text-ink-red-8'">{{ c.passed ? '✓' : '✗' }} {{ checkText(c.check) }}</li>
          </ul>
          <p v-if="shown(e)" class="text-xs text-ink-gray-5">Ran against {{ shown(e).source === 'recorded' ? 'the recorded answer' : 'the model' }}.</p>
        </div>
      </Card>
      <Card v-else><Empty title="No examples yet." hint="An example is a sample capture and what the skill must make of it. It is how a changed text is tested before it is saved." /></Card>
    </section>

    <section class="flex flex-col gap-2" data-skill-lessons>
      <h2 class="text-base-medium text-ink-gray-9">Lessons <span class="text-sm font-normal text-ink-gray-6">What your corrections in Needs you taught this skill. They change its words, nothing else.</span></h2>
      <Card v-if="d.lessons.length" flush>
        <LessonCard v-for="l in d.lessons" :key="l.name" :lesson="l" :can-edit="d.can_edit" @changed="load" />
      </Card>
      <Card v-else><Empty title="No lessons yet." hint="When you correct this skill's guesses in Needs you the same way three times, it proposes a lesson here." /></Card>
    </section>

    <section class="flex flex-col gap-2" data-skill-versions>
      <h2 class="text-base-medium text-ink-gray-9">Versions</h2>
      <Card flush>
        <div v-for="(v, i) in d.versions" :key="v.version" class="flex flex-col gap-1 border-b border-outline-gray-1 py-3 last:border-0" data-skill-version-row :data-version="v.version">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-base-medium text-ink-gray-9">Version {{ v.version }}</span><Badge v-if="i === 0" theme="green" label="Current" />
            <span class="flex-1 text-sm text-ink-gray-6">{{ v.changed_by_name }} · {{ dateTime(v.changed_on) }}<template v-if="v.note"> · {{ v.note }}</template></span>
            <Button v-if="i < d.versions.length - 1" size="sm" :label="open === v.version ? 'Hide change' : 'Show change'" data-version-diff @click="open = open === v.version ? null : v.version" />
            <Button v-if="d.can_edit && i > 0" size="sm" label="Roll back" data-version-rollback @click="rollback(v)" />
          </div>
          <DiffView v-if="open === v.version" :before="d.versions[i + 1]?.instructions" :after="v.instructions" />
        </div>
      </Card>
    </section>

    <section class="flex flex-col gap-2" data-skill-runs>
      <h2 class="text-base-medium text-ink-gray-9">Recent runs</h2>
      <Card v-if="d.runs.length" flush>
        <button v-for="r in d.runs" :key="r.name" type="button" class="flex w-full flex-wrap items-center gap-2 border-b border-outline-gray-1 py-2.5 text-left last:border-0 hover:bg-surface-gray-1 focus-visible:focus-ring" data-skill-run @click="openRun(r)">
          <Badge :theme="STATUS[r.status] || 'gray'" :label="r.status" />
          <span class="flex-1 text-sm text-ink-gray-8">{{ r.trigger }} · v{{ r.skill_version }} · {{ dateTime(r.creation) }}</span>
          <span class="text-sm tabular-nums text-ink-gray-6">${{ (r.cost || 0).toFixed(4) }}</span>
        </button>
      </Card>
      <Card v-else><Empty title="No runs yet." hint="Each time this skill runs, what it did and what it cost is listed here." /></Card>
    </section>
  </div>
  <div v-else-if="missing" class="page-body" data-skill-missing><Empty title="There is no such skill." hint="Go back to the list of skills." /></div>

  <Dialog v-model:open="logOpen" title="Run log">
    <template #default>
      <div v-if="log" class="flex flex-col gap-2 text-sm" data-run-log>
        <p class="text-ink-gray-7">{{ log.status }} · version {{ log.version }} · {{ log.trigger }} · {{ log.duration }}s · ${{ (log.cost || 0).toFixed(4) }} · {{ log.input_tokens }} in, {{ log.output_tokens }} out</p>
        <p v-if="log.error" class="text-ink-red-8">{{ log.error }}</p>
        <p v-if="log.input" class="text-ink-gray-6">Input: {{ log.input }}</p>
        <div v-if="log.tool_calls.length"><b class="text-ink-gray-8">Tools</b>
          <div v-for="(c, i) in log.tool_calls" :key="i" class="text-ink-gray-7">{{ c.tool }}<span v-if="c.refused" class="text-ink-red-8"> (refused)</span></div></div>
        <pre v-if="log.output" class="max-h-64 overflow-auto whitespace-pre-wrap rounded-4 bg-surface-gray-1 p-2 text-xs">{{ log.output }}</pre>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
// A skill page (issue 28): its instructions (editable, with a preview), its examples with Test (pass or fail before saving), its versions with
// a diff and Roll back, and its recent runs, each opening its log.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Dialog, FormControl, Switch } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import DiffView from '@/components/DiffView.vue'
import Empty from '@/components/Empty.vue'
import LessonCard from '@/components/brain/LessonCard.vue'
import Md from '@/components/Md.vue'
import PageHead from '@/components/PageHead.vue'
import { api, tryCall } from '@/lib/api'
import { dateTime } from '@/lib/dates'

const props = defineProps({ name: String })
const router = useRouter()
const STATUS = { Done: 'green', Failed: 'red', Skipped: 'gray', Running: 'blue', Queued: 'gray' }
const d = ref(null)
const missing = ref(false)
const text = ref('')
const preview = ref(false)
const testing = ref(false)
const results = ref({})
const open = ref(null)
const log = ref(null)
const logOpen = ref(false)
const dirty = computed(() => d.value && text.value !== d.value.instructions)
const shown = (e) => results.value[e.title]
function checkText(c) {
  const [k, v] = Object.entries(c)[0]
  const w = { summary_contains: (x) => `the summary mentions "${x}"`, has_proposal: (x) => `proposes ${[x.kind, x.area && `in ${x.area}`, x.title_contains && `about "${x.title_contains}"`].filter(Boolean).join(' ')}`,
    no_proposal: (x) => (x.kind ? `proposes no ${x.kind}` : 'proposes nothing'), proposal_count: (x) => `between ${x.min ?? 0} and ${x.max ?? 'any number of'} proposals` }
  return (w[k] || (() => k))(v)
}

async function load() {
  const res = await tryCall(() => api('skills.detail', { name: props.name }))
  if (!res) { missing.value = true; return }
  d.value = res
  text.value = res.instructions || ''
}
watch(() => props.name, () => { results.value = {}; load() }, { immediate: true })

async function toggle(on) {
  const res = await tryCall(() => api('skills.set_active', { name: d.value.name, active: on ? 1 : 0 }))
  if (res) d.value.active = res.active
}
async function save() {
  const res = await tryCall(() => api('skills.save', { name: d.value.name, values: JSON.stringify({ instructions: text.value }) }), 'Saved as a new version.')
  if (res) { results.value = {}; await load() }
}
async function runTest() {
  testing.value = true
  try {
    const res = await tryCall(() => api('skills.test', { name: d.value.name, instructions: text.value }))
    if (res) results.value = Object.fromEntries(res.results.map((r) => [r.title, r]))
  } finally { testing.value = false }
}
async function rollback(v) {
  const res = await tryCall(() => api('skills.rollback', { name: d.value.name, version: v.version }), `Rolled back to version ${v.version}.`)
  if (res) await load()
}
async function takeUpdate() {
  const res = await tryCall(() => api('skills.accept_update', { name: d.value.name }), 'Updated. Your earlier text is in the versions.')
  if (res) await load()
}
async function openRun(r) {
  log.value = await tryCall(() => api('skills.run_log', { run: r.name }))
  logOpen.value = !!log.value
}
</script>
