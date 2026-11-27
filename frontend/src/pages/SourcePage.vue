<template>
  <PageHead :title="d?.title || 'Source'" :path="[{ label: 'Brain', to: '/brain' }, { label: 'Sources', to: '/brain/sources' }]"
    :sub="d ? (d.group === 'kind' ? 'A kind: what it is' : 'A channel: where it comes from') : ''">
    <Switch v-if="d && d.connection && !d.strip.always_on" :model-value="!!d.strip.active" :disabled="!writable" :label="d.strip.active ? 'On' : 'Off'" data-source-active @update:model-value="toggle" />
  </PageHead>
  <div v-if="d" class="page-body flex max-w-5xl flex-col gap-4" data-source-page :data-source="d.key" :data-skill="d.skill" :data-version="d.version">
    <!-- the strip -->
    <Card class="grid grid-cols-2 gap-x-4 gap-y-3 md:grid-cols-6" data-source-strip>
      <div v-for="s in strip" :key="s.key" class="min-w-0"><div class="text-xs text-ink-gray-5">{{ s.label }}</div>
        <div class="truncate text-base-medium text-ink-gray-9" :data-strip="s.key">{{ s.value }}</div></div>
    </Card>
    <TabBar :tabs="TABS" :model-value="tab" label="This source" data-source-tabs @update:model-value="setTab" />

    <AgentPanel v-if="tab === 'agent'" :key-name="d.key" :writable="writable" data-tab-panel="agent" @changed="load" />

    <!-- Overview -->
    <section v-if="tab === 'overview'" class="flex flex-col gap-3" data-tab-panel="overview">
      <Card class="flex flex-col gap-2">
        <SectionHead>What arrives</SectionHead>
        <Md :text="d.description || 'Nothing described yet.'" />
        <p class="text-sm text-ink-gray-6">Everything that arrives is read with the shared rules, then <template v-if="d.group === 'kind'">the rules of the channel it came by, then these.</template><template v-else>these, then the rules of its kind.</template>
          One skill, <RouterLink class="underline" :to="`/brain/skills/${d.skill}`">{{ d.skill }}</RouterLink>, holds them.</p>
      </Card>
      <Card v-if="d.how_to_connect && !d.connection && !d.strip.always_on" class="flex flex-col gap-2" data-source-connect>
        <SectionHead>Nothing yet</SectionHead>
        <p class="text-sm text-ink-gray-7">{{ d.how_to_connect }}</p>
        <div><Button label="Connect it" icon-left="lucide-plus" :route="'/brain/sources'" data-source-connect-go /></div>
      </Card>
      <Card v-else-if="!d.recent.length" class="flex flex-col gap-1" data-source-nothing>
        <SectionHead>Nothing yet</SectionHead>
        <p class="text-sm text-ink-gray-7">{{ d.how_to_connect || 'Things of this kind that you add or connect will show up here.' }} Try it shows what these rules would do first.</p>
      </Card>
    </section>

    <!-- Rules -->
    <div v-if="tab === 'rules'" class="flex flex-col gap-4" data-tab-panel="rules">
      <SourceRules :source-key="d.key" :writable="writable" />
      <SectionHead data-reading-rules>How the Brain reads it</SectionHead>
      <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div class="flex min-w-0 flex-col gap-3">
        <Card v-for="s in sections" :key="s.title" class="flex flex-col gap-2" data-rule-section :data-section="s.title">
          <SectionHead>{{ s.title }}</SectionHead>
          <template v-if="s.mode === 'chips'">
            <div class="flex flex-wrap gap-1.5">
              <span v-for="(c, i) in s.items" :key="c + i" class="inline-flex max-w-full items-center gap-1 rounded-full bg-surface-gray-2 py-0.5 pl-2.5 pr-1 text-sm text-ink-gray-8" data-chip>
                <span class="min-w-0 break-words">{{ c }}</span>
                <button v-if="writable" type="button" class="flex size-5 flex-none items-center justify-center rounded-full hover:bg-surface-gray-3 focus-visible:focus-ring" :aria-label="`Remove ${c}`" data-chip-remove @click="s.items.splice(i, 1)"><span class="lucide-x size-3.5" aria-hidden="true" /></button>
              </span>
              <span v-if="!s.items.length" class="text-sm text-ink-gray-5">Nothing listed.</span>
            </div>
            <form v-if="writable" class="flex gap-2" @submit.prevent="addChip(s)"><TextInput v-model="s.draft" class="min-w-0 flex-1" :placeholder="`Add to ${s.title}`" :aria-label="`Add to ${s.title}`" data-chip-input />
              <Button type="submit" label="Add" data-chip-add /></form>
          </template>
          <template v-else-if="s.mode === 'rows'">
            <div v-for="(r, i) in s.items" :key="i" class="flex items-center gap-2" data-row-line>
              <TextInput v-model="s.items[i]" class="min-w-0 flex-1" :disabled="!writable" :aria-label="`${s.title} ${i + 1}`" />
              <Button v-if="writable" variant="ghost" icon="lucide-x" :aria-label="`Remove ${s.title} ${i + 1}`" @click="s.items.splice(i, 1)" />
            </div>
            <div v-if="writable"><Button size="sm" label="Add a row" icon-left="lucide-plus" data-row-add @click="s.items.push('')" /></div>
          </template>
          <Textarea v-else v-model="s.text" :rows="3" class="w-full" :disabled="!writable" :aria-label="s.title" />
        </Card>
        <Card class="flex flex-col gap-2" data-rule-section data-section="Anything else">
          <SectionHead>Anything else?</SectionHead>
          <Textarea v-model="anything" :rows="3" class="w-full" :disabled="!writable" placeholder="A rule in your own words, for example: ask me before filing anything over Rs 1,00,000." aria-label="Anything else" data-rules-anything />
        </Card>
        <div class="flex flex-wrap items-center gap-2">
          <Button v-if="writable" variant="solid" :label="`Save as version ${d.version + 1}`" :disabled="!dirty" :loading="saving" data-rules-save @click="saveRules" />
          <span v-if="dirty" class="text-sm text-ink-amber-9">Not saved yet.</span>
          <span v-else class="text-sm text-ink-gray-6" data-rules-version>Version {{ d.version }}</span>
        </div>
        <Card class="flex flex-col gap-1" data-version-history>
          <SectionHead>Version history</SectionHead>
          <Row bare v-for="v in d.versions" :key="v.version" class="flex flex-wrap items-center gap-2 py-2 text-sm" data-version-row :data-version="v.version">
            <span class="w-20 text-ink-gray-9">Version {{ v.version }}</span><span class="min-w-0 flex-1 text-ink-gray-6">{{ v.changed_by }} · {{ v.changed_on }} · {{ v.note }}</span>
            <Badge v-if="v.version === d.version" theme="green" label="Now" />
            <Button v-else-if="writable" size="sm" label="Go back to this" data-version-back @click="goBack(v)" />
          </Row>
        </Card>
      </div>
      <aside class="flex flex-col gap-3" data-source-side>
        <Card class="flex flex-col gap-3">
          <SectionHead>Files without you</SectionHead>
          <FormControl v-model="confidence" type="number" label="Above this confidence" :disabled="!writable" min="0" max="100" data-confidence />
          <p class="text-sm text-ink-gray-6">Out of 100. Only kinds of proposal you let the Brain file in Settings are filed this way{{ d.settings.own ? '' : '; until you set it, this follows Settings' }}.</p>
          <SectionHead>Agents that may read it</SectionHead>
          <EmptyState v-if="!agents.length" line="No agents yet." />
          <label v-for="a in agents" :key="a.user" class="flex items-center gap-2 text-sm text-ink-gray-8" data-reader><Checkbox v-model="a.allowed" :disabled="!writable" :aria-label="a.name" />{{ a.name }}</label>
          <div v-if="writable"><Button label="Save" :disabled="!sideDirty" data-settings-save @click="saveSide" /></div>
        </Card>
      </aside>
      </div>
    </div>

    <!-- Examples and lessons -->
    <section v-if="tab === 'examples'" class="flex flex-col gap-3" data-tab-panel="examples">
      <Card class="flex flex-col gap-1" data-source-examples>
        <SectionHead>Examples</SectionHead>
        <Row bare v-for="e in d.examples" :key="e.title" class="flex items-center gap-2 py-2 text-sm"><span class="flex-1 text-ink-gray-9">{{ e.title }}</span><Badge v-if="e.last_result" :theme="e.last_result === 'Pass' ? 'green' : 'red'" :label="e.last_result" /></Row>
        <EmptyState line="No examples yet. Each is a sample and what the rules must make of it. Try it can teach one." v-if="!d.examples.length" />
      </Card>
      <Card class="flex flex-col gap-1" data-source-lessons>
        <SectionHead>Lessons</SectionHead>
        <Row bare v-for="l in lessons" :key="l" class="py-2 text-sm text-ink-gray-8" data-lesson-line>{{ l }}</Row>
        <EmptyState line="No lessons yet. What your corrections teach this source shows here. Try it can turn one into a lesson." v-if="!lessons.length" />
        <div class="pt-1"><RouterLink class="text-sm underline" :to="`/brain/skills/${d.skill}`">Open the skill</RouterLink></div>
      </Card>
    </section>

    <!-- Activity -->
    <section v-if="tab === 'activity'" data-tab-panel="activity">
      <Card v-if="d.recent.length" flush>
        <Row bare v-for="r in d.recent" :key="r.name" :pane="`inbox:${r.name}`" :label="r.title" class="flex flex-wrap items-center gap-2 py-2.5 text-sm" data-activity-line>
          <span class="min-w-0 flex-1 truncate text-ink-gray-9">{{ r.title }}</span><span class="text-ink-gray-6">{{ r.kind }} · {{ r.received }}</span><Badge :theme="r.status === 'Failed' ? 'red' : r.status === 'Done' ? 'green' : 'amber'" :label="r.status" />
        </Row>
      </Card>
      <Card v-else data-activity-empty><EmptyState :line="`Nothing yet. ${d.how_to_connect || 'Things of this kind that you add or connect will show up here.'}`" /></Card>
    </section>

    <!-- Try it -->
    <section v-if="tab === 'try' && d.key === 'gmail'" class="flex flex-col gap-3" data-tab-panel="try">
      <!-- issue 101: for Gmail, Try it is a live search of the connected inbox. It shows the five newest matches and files nothing. -->
      <Card class="flex flex-col gap-3" data-mail-try>
        <p class="text-sm text-ink-gray-7">Search your connected inbox live. It shows the five newest matches and files nothing.</p>
        <form class="flex gap-2" @submit.prevent="searchMail"><TextInput v-model="mailQuery" class="min-w-0 flex-1" placeholder="A word, a sender or a subject" aria-label="Search the inbox" data-mail-query />
          <Button type="submit" variant="solid" label="Search" icon-left="lucide-search" :loading="searching" data-mail-search /></form>
        <p v-if="mailError" class="text-sm text-ink-red-4" data-mail-error>{{ mailError }}</p>
        <div v-if="mailHits" class="flex flex-col" data-mail-hits>
          <EmptyState v-if="!mailHits.length" line="Nothing matches." data-mail-none />
          <Row bare v-for="h in mailHits" :key="h.thread_id" class="flex flex-col gap-0.5 py-2 text-sm" data-mail-hit>
            <span class="text-ink-gray-9" data-mail-subject>{{ h.subject || '(no subject)' }}</span><span class="text-ink-gray-6">{{ h.from }} · {{ h.date }}</span></Row>
        </div>
      </Card>
    </section>
    <section v-else-if="tab === 'try'" class="flex flex-col gap-3" data-tab-panel="try">
      <Card class="flex flex-col gap-3" data-try-form>
        <p class="text-sm text-ink-gray-7">Drop or pick a sample. It shows what these rules would do with it, and files nothing.</p>
        <label class="flex cursor-pointer flex-col items-center gap-1 rounded-5 border border-dashed border-outline-gray-3 px-4 py-6 text-center text-sm text-ink-gray-7 hover:bg-surface-gray-1" data-try-drop
          @dragover.prevent @drop.prevent="(e) => pick(e.dataTransfer.files?.[0])">
          <span class="lucide-upload size-5" aria-hidden="true" />{{ file ? file.name : 'Drop a file here, or pick one' }}
          <input type="file" class="sr-only" data-try-file @change="(e) => pick(e.target.files?.[0])" />
        </label>
        <Textarea v-model="sample.text" :rows="4" class="w-full" placeholder="Or paste some text" aria-label="Sample text" data-try-text />
        <TextInput v-model="sample.url" placeholder="Or a link" aria-label="Sample link" data-try-url />
        <div><Button variant="solid" label="Try it" icon-left="lucide-play" :loading="trying" :disabled="!writable || uploading" data-try-run @click="tryIt" /></div>
      </Card>
      <Card v-if="result" class="flex flex-col gap-3" data-try-result>
        <div><SectionHead>Summary</SectionHead><p class="text-sm text-ink-gray-8" data-try-summary>{{ result.summary || 'No summary.' }}</p></div>
        <div v-if="result.transcript"><SectionHead>Transcript</SectionHead><Md :text="result.transcript" class="text-sm" /></div>
        <div data-try-proposals><SectionHead>What it would file</SectionHead>
          <p v-if="!result.proposals.length" class="text-sm text-ink-gray-6">Nothing. It would only keep it with its summary.</p>
          <Row bare v-for="(p, i) in result.proposals" :key="i" class="flex flex-wrap items-center gap-2 py-1.5 text-sm" data-try-proposal>
            <Badge theme="gray" :label="p.kind" /><span class="min-w-0 flex-1 text-ink-gray-9">{{ p.title }}</span><span class="text-ink-gray-6">{{ p.confidence }}%</span>
            <Badge :theme="p.files_alone ? 'green' : 'amber'" :label="p.files_alone ? 'Files without you' : 'Needs you'" /></Row></div>
        <div v-if="result.skipped.length" data-try-skipped><SectionHead>What it skipped</SectionHead><ul class="list-disc pl-5 text-sm text-ink-gray-8"><li v-for="x in result.skipped" :key="x">{{ x }}</li></ul></div>
        <div data-try-lessons><SectionHead>Lessons used</SectionHead>
          <p v-if="!result.lessons_used.length" class="text-sm text-ink-gray-6">None yet.</p><ul v-else class="list-disc pl-5 text-sm text-ink-gray-8"><li v-for="x in result.lessons_used" :key="x">{{ x }}</li></ul></div>
        <p class="text-xs text-ink-gray-5">Read with {{ result.skills_used }} · cost ${{ result.cost }}</p>
        <div class="flex flex-wrap gap-2">
          <Button v-if="writable" label="That's wrong… teach it" icon-left="lucide-graduation-cap" data-try-teach @click="teachOpen = true" />
          <Button v-if="writable" variant="solid" label="File it for real" data-try-file-it :loading="filing" @click="fileIt" />
        </div>
      </Card>
    </section>
  </div>
  <Card v-else-if="missing" class="m-4"><EmptyState line="There is no such source. Open Brain, Sources to see the ones there are." /></Card>

  <Dialog v-model:open="teachOpen" title="Teach it" :actions="[{ label: 'Add the lesson', variant: 'solid', onClick: teach }]">
    <template #default><div class="flex flex-col gap-2" data-teach>
      <FormControl v-model="lesson" type="textarea" :rows="3" label="What should it have done?" placeholder="For example: A receipt from the chemist is Health, not Money." />
      <p class="text-sm text-ink-gray-6">It becomes one line under Lessons in this source's skill, as a new version.</p></div></template>
  </Dialog>
</template>
<script setup>
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import RefLink from '@/components/ui/RefLink.vue'
// One source (issue 84): a channel (where it comes from) or a kind (what it is), as one page in one template: a strip, then Overview, Rules,
// Examples & lessons, Activity and Try it. Rules show the source's skill as fields and save as a new version of it.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Checkbox, Dialog, FormControl, Switch, TextInput, Textarea } from 'frappe-ui'
import AgentPanel from '@/components/brain/AgentPanel.vue'
import SourceRules from '@/components/brain/SourceRules.vue'
import Card from '@/components/ui/Card.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Md from '@/components/Md.vue'
import PageHead from '@/components/PageHead.vue'
import TabBar from '@/components/TabBar.vue'
import { errorText, tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { canWrite, store } from '@/lib/store'
import { uploadFile } from '@/lib/upload'

const BASE_TABS = [{ value: 'overview', label: 'Overview' }, { value: 'rules', label: 'Rules' }, { value: 'examples', label: 'Examples & lessons' },
  { value: 'activity', label: 'Activity' }, { value: 'try', label: 'Try it' }]
const route = useRoute()
const router = useRouter()
const d = ref(null)
const missing = ref(false)
const sections = ref([])
const anything = ref('')
const confidence = ref(80)
const agents = ref([])
const saving = ref(false)
const baseline = ref('')
const sideBaseline = ref('')
const file = ref(null)
const fileUrl = ref('')
const sample = ref({ text: '', url: '' })
const result = ref(null)
const trying = ref(false)
const uploading = ref(false)
const filing = ref(false)
const teachOpen = ref(false)
const lesson = ref('')
const mailQuery = ref('')
const mailHits = ref(null)
const mailError = ref('')
const searching = ref(false)
const writable = computed(() => canWrite() && !store.isAgent && !!d.value?.can_edit)
// an agent has one more tab (issue 85): what it knows, can do, did and waits for, and it opens on it
const TABS = computed(() => (d.value?.is_agent ? [{ value: 'agent', label: 'Your agent' }, ...BASE_TABS] : BASE_TABS))
const tab = computed(() => (TABS.value.some((t) => t.value === route.query.tab) ? route.query.tab : d.value?.is_agent ? 'agent' : 'overview'))
const setTab = (v) => router.replace({ query: { ...route.query, tab: v === TABS.value[0].value ? undefined : v } })

const strip = computed(() => {
  const s = d.value.strip
  return [{ key: 'on', label: 'Status', value: s.always_on ? 'Always on' : s.active ? 'On' : 'Off' }, { key: 'from', label: 'Arrives from', value: s.arrives_from },
    { key: 'week', label: 'This week', value: s.this_week ? String(s.this_week) : 'Nothing yet' },
    { key: 'filed', label: 'Filed without you', value: s.filed_without_you === null ? '—' : `${s.filed_without_you}%` },
    { key: 'cost', label: 'AI cost this week', value: `$${s.cost_week.toFixed(2)}` }, { key: 'skill', label: 'Skill', value: s.skill_label }]
})
const shape = () => JSON.stringify([sections.value.map((s) => [s.items, s.text]), anything.value])
const dirty = computed(() => d.value && shape() !== baseline.value)
const sideShape = () => JSON.stringify([confidence.value, agents.value.map((a) => a.allowed)])
const sideDirty = computed(() => d.value && sideShape() !== sideBaseline.value)
const lessons = computed(() => d.value?.lessons_text || [])

function fill(res) {
  d.value = res
  sections.value = res.rules.sections.map((s) => ({ ...s, items: [...s.items], draft: '' }))
  anything.value = res.rules.anything_else || ''
  confidence.value = res.settings.auto_file_confidence
  agents.value = res.settings.agents.map((a) => ({ ...a }))
  baseline.value = shape()
  sideBaseline.value = sideShape()
}
async function load() {
  const res = await tryCall(() => brainData.sourcePage.get({ key: route.params.key, space: store.space }))
  if (!res) { missing.value = true; return }
  fill(res)
}
// another source starts clean; the space settling after the page opened only reads the page again, so a Try it result is not lost
watch(() => route.params.key, () => { d.value = null; missing.value = false; result.value = null; load() }, { immediate: true })
watch(() => store.space, () => { if (d.value) load() })

function addChip(s) {
  const v = (s.draft || '').trim()
  if (v && !s.items.includes(v)) s.items.push(v)
  s.draft = ''
}
async function saveRules() {
  saving.value = true
  try {
    const map = Object.fromEntries(sections.value.map((s) => [s.title, s.mode === 'text' ? s.text : s.items.map((x) => x.trim()).filter(Boolean)]))
    const res = await tryCall(() => brainData.sourcePage.save_rules({ key: d.value.key, sections: JSON.stringify(map), anything_else: anything.value, space: store.space }), 'Saved as a new version.')
    if (res) await load()
  } finally { saving.value = false }
}
async function goBack(v) {
  const res = await tryCall(() => brainData.sourcePage.go_back({ key: d.value.key, version: v.version, space: store.space }), `Went back to version ${v.version}, as a new version.`)
  if (res) await load()
}
async function saveSide() {
  const res = await tryCall(() => brainData.sourcePage.save_settings({ key: d.value.key, auto_file_confidence: Number(confidence.value), readers: JSON.stringify(agents.value.filter((a) => a.allowed).map((a) => a.user)), space: store.space }), 'Saved.')
  if (res) await load()
}
async function toggle(on) {
  const c = d.value.connection
  if (await tryCall(() => brainData.connections.save({ name: c.name, active: on ? 1 : 0 }), on ? `${d.value.title} is on.` : `${d.value.title} is off.`)) await load()
}
async function pick(f) {
  if (!f) return
  file.value = f
  fileUrl.value = ''
  uploading.value = true
  try {
    const up = await tryCall(() => uploadFile(f))
    fileUrl.value = up?.file_url || ''
    if (!fileUrl.value) file.value = null
  } finally { uploading.value = false }
}
const args = () => ({ key: d.value.key, title: file.value?.name || '', text: sample.value.text, url: sample.value.url, file_url: fileUrl.value, space: store.space })
async function tryIt() {
  trying.value = true
  try { result.value = (await tryCall(() => brainData.sourcePage.try_it(args()))) || result.value } finally { trying.value = false }
}
// Gmail's Try it: the live search the assistant uses, on this person's inboxes; the answer's own words when it cannot
async function searchMail() {
  if (!mailQuery.value.trim()) return
  searching.value = true
  mailError.value = ''
  try {
    const res = await brainData.mail.search({ fields: { text: mailQuery.value.trim() }, max: 5, space: store.space })
    mailHits.value = res.hits
    if (res.errors?.length) mailError.value = res.errors.map((e) => `${e.inbox}: ${e.error}`).join('. ')
  } catch (e) { mailHits.value = null; mailError.value = errorText(e) } finally { searching.value = false }
}
async function fileIt() {
  filing.value = true
  try {
    if (await tryCall(() => brainData.sourcePage.file_it(args()), 'Filed. The Brain is reading it now.')) { result.value = null; file.value = null; fileUrl.value = ''; sample.value = { text: '', url: '' }; await load() }
  } finally { filing.value = false }
}
async function teach() {
  const res = await tryCall(() => brainData.sourcePage.teach({ key: d.value.key, lesson: lesson.value, space: store.space }), 'Added as a lesson.')
  if (!res) return
  teachOpen.value = false
  lesson.value = ''
  await load()
  if (result.value) result.value.lessons_used = res.lessons
}
</script>
