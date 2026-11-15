<template>
  <template v-if="item">
    <PageHead v-if="page" :title="item.title" :crumb="{ to: '/inbox', label: 'Inbox', here: item.source_type }">
      <template #sub><span class="flex flex-wrap items-center gap-1">{{ headParts.text }}<template v-if="headParts.who"> · {{ headParts.verb }}
        <Avatar size="xs" :label="headParts.who" />{{ headParts.who }}</template></span></template>
      <template v-if="pending.length && writable">
        <Button label="Reject all" @click="decideAll('reject')" />
        <Button variant="solid" :label="`Accept all ${pending.length} pending`" @click="decideAll('accept')" />
      </template>
      <Button v-else-if="item.status === 'Failed' && writable" variant="solid" label="Retry" @click="retry" />
    </PageHead>
    <div v-else-if="writable && (pending.length || item.status === 'Failed')" class="flex flex-wrap items-center justify-end gap-2">
      <template v-if="pending.length">
        <Button label="Reject all" @click="decideAll('reject')" />
        <Button variant="solid" :label="`Accept all ${pending.length} pending`" @click="decideAll('accept')" />
      </template>
      <Button v-else variant="solid" label="Retry" @click="retry" />
    </div>

    <div :class="page ? 'page-body' : 'flex flex-col gap-4'">
      <Alert v-if="item.status === 'Failed'" theme="red" title="Processing failed." :description="item.error" />
      <Alert v-else-if="item.status === 'New' || item.status === 'Processing'" :title="item.status === 'New' ? 'Waiting for an agent.' : 'An agent is processing this.'"
        description="The summary and proposals show here when it is done." />
      <div class="cols">
        <div class="half">
          <section>
            <SectionHead>Original</SectionHead>
            <div v-if="!item.files.length && !item.raw_text" class="grid min-h-[120px] place-items-center rounded-5 border border-dashed border-outline-gray-3 bg-surface-gray-1 text-base text-ink-gray-6"><span>No file was attached.</span></div>
            <div v-for="f in item.files" :key="f.file_url" class="mb-3">
              <template v-if="fileKind(f.file_name) === 'image'">
                <div class="max-h-[520px] overflow-auto rounded-5 border border-outline-gray-1 bg-surface-gray-1" :class="zoom ? 'cursor-zoom-out' : 'cursor-zoom-in'" @click="zoom = !zoom">
                  <img class="block h-auto" :class="zoom ? 'w-[220%] max-w-none' : 'w-full'" :src="item.files.length === 1 && item.preview_image ? item.preview_image : f.file_url" :alt="f.file_name" />
                </div>
              </template>
              <audio v-else-if="fileKind(f.file_name) === 'audio'" :src="f.file_url" controls class="w-full"></audio>
              <object v-else-if="fileKind(f.file_name) === 'pdf'" :data="f.file_url" type="application/pdf" class="block h-[520px] w-full rounded-5 border border-outline-gray-1">
                <a class="text-ink-blue-8 hover:underline" :href="f.file_url" target="_blank" rel="noopener">Open {{ f.file_name }}</a>
              </object>
              <div class="mt-1.5 text-sm text-ink-gray-6">
                <a class="text-ink-blue-8 hover:underline" :href="f.file_url" target="_blank" rel="noopener">{{ f.file_name }}</a> · {{ fileSize(f.file_size) }}
                <span v-if="fileKind(f.file_name) === 'image'"> · click the image to zoom</span>
              </div>
            </div>
            <Card v-if="item.raw_text" class="mt-2"><Md :text="item.raw_text" /></Card>
          </section>
          <section v-if="item.transcript_md || editingTranscript">
            <SectionHead>Transcript
              <template v-if="writable && !editingTranscript" #action><Button variant="ghost" size="sm" label="Edit" @click="startTranscript" /></template>
            </SectionHead>
            <Card>
              <template v-if="editingTranscript">
                <Textarea v-model="transcriptDraft" :rows="12" aria-label="Transcript" />
                <div class="mt-2 flex justify-end gap-2">
                  <Button label="Cancel" @click="editingTranscript = false" />
                  <Button variant="solid" label="Save transcript" @click="saveTranscript" />
                </div>
              </template>
              <Md v-else :text="item.transcript_md" />
            </Card>
            <p v-if="(item.transcript_md || '').includes('[?]')" class="mt-2 text-sm text-ink-gray-6">Words marked [?] were hard to read. Edit the transcript to correct them.</p>
          </section>
        </div>

        <div class="half">
          <section v-if="item.summary_md">
            <SectionHead>Summary</SectionHead>
            <Card><Md :text="item.summary_md" /></Card>
          </section>
          <section>
            <SectionHead ref="proposalsHead" data-proposals>Proposals<template v-if="item.proposals.length"> · {{ countsLine }}</template></SectionHead>
            <div class="flex flex-col gap-3">
              <Card v-for="p in item.proposals" :key="p.name" class="flex flex-col gap-2" :tint="p.status !== 'Pending'" :data-proposal="p.status">
                <div class="flex items-start gap-2">
                  <Badge :theme="p.kind === 'Task' ? 'blue' : 'gray'" :label="KIND_LABEL[p.kind] || p.kind" />
                  <div class="min-w-0 flex-1 break-words text-base-medium text-ink-gray-9">{{ p.preview }}</div>
                  <Badge v-if="p.status === 'Accepted'" theme="green" label="Accepted" />
                  <Badge v-else-if="p.status === 'Rejected'" label="Rejected" />
                  <Badge v-else-if="p.confidence < 0.6" theme="amber" :label="`${pct(p.confidence)}% sure`" />
                  <span v-else class="whitespace-nowrap text-sm text-ink-gray-6">{{ pct(p.confidence) }}% sure</span>
                </div>
                <template v-if="p.status === 'Pending'">
                  <div v-if="p.confidence < 0.6 || p.error" class="text-sm" :class="p.error ? 'text-ink-red-8' : 'text-ink-gray-6'">
                    {{ p.error || 'The agent was not sure about this one. Edit it or reject it.' }}
                  </div>
                  <div class="flex flex-wrap items-center gap-2">
                    <template v-if="p.filed || p.kind === 'Month Goal'">
                      <Pick :model-value="p.payload.area || null" :options="areaOptions" placeholder="area" :disabled="!writable"
                        @update:model-value="(v) => setField(p, 'area', v)" />
                    </template>
                    <Badge v-if="p.payload.goal" size="lg" :label="'Goal: ' + goalTitle(p.payload.goal)" />
                    <template v-if="p.filed">
                      <Pick v-if="p.payload.project || projectOptions(p).length" :model-value="p.payload.project || null" :options="projectOptions(p)"
                        prefix="Project: " placeholder="project" :disabled="!writable" @update:model-value="(v) => setField(p, 'project', v)" />
                      <Badge v-for="a in p.payload.also_in || []" :key="a" size="lg">also in {{ areaName(a) }}
                        <template v-if="writable" #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" :label="'Remove also in ' + areaName(a)"
                          @click="setField(p, 'also_in', p.payload.also_in.filter((x) => x !== a))" /></template></Badge>
                      <Pick :model-value="null" :options="areaOptions.filter((o) => o.value !== p.payload.area && !(p.payload.also_in || []).includes(o.value))"
                        placeholder="also in" :clearable="false" :disabled="!writable" @update:model-value="(v) => setField(p, 'also_in', [...(p.payload.also_in || []), v])" />
                      <Badge v-for="t in p.payload.tags || []" :key="tagKey(t)" size="lg">#{{ tagName(t) }}
                        <template v-if="writable" #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" :label="'Remove #' + tagName(t)"
                          @click="setField(p, 'tags', p.payload.tags.filter((x) => tagKey(x) !== tagKey(t)))" /></template></Badge>
                      <Pick :model-value="null" :options="tagOptions(p)" placeholder="tag" :clearable="false" :disabled="!writable"
                        @update:model-value="(v) => setField(p, 'tags', [...(p.payload.tags || []), v])" />
                    </template>
                    <template v-if="p.kind === 'Task'">
                      <span v-if="p.payload.due_date || dueFor === p.name" class="inline-flex items-center gap-1.5 text-sm text-ink-gray-6">due
                        <DatePicker class="w-36" size="sm" :model-value="p.payload.due_date || ''" clearable :disabled="!writable" aria-label="Due date"
                          @update:model-value="(v) => setField(p, 'due_date', v || null)" /></span>
                      <Button v-else size="sm" variant="outline" icon-left="lucide-plus" label="due date" :disabled="!writable" @click="dueFor = p.name" />
                    </template>
                    <Badge v-for="c in factChips(p)" :key="c" size="lg" :label="c" />
                  </div>
                  <div v-if="writable" class="flex items-center justify-end gap-2">
                    <Button variant="ghost" label="Reject" @click="decide(p, 'reject')" />
                    <Button label="Edit" @click="openEdit(p)" />
                    <Button variant="solid" label="Accept" @click="decide(p, 'accept')" />
                  </div>
                </template>
                <div v-else-if="p.status === 'Accepted'" class="text-sm text-ink-gray-6">
                  Filed as {{ (p.created_doctype || '').replace('Life ', '').toLowerCase() }}.
                  <a v-if="p.route && p.exists" href="#" class="text-ink-blue-8 underline" @click.prevent="openRoute(p.route)">Open</a>
                </div>
              </Card>
              <Card v-if="!item.proposals.length"><Empty title="No proposals."
                :hint="item.status === 'To Review' || item.status === 'Done' ? 'The agent found nothing to file from this item.' : 'Proposals appear here once an agent has processed the item.'" /></Card>
            </div>
            <p class="mt-3 text-sm text-ink-gray-6">Nothing here becomes a record until you accept it. The original is always kept.</p>
          </section>
          <Backlinks doctype="Life Inbox Item" :name="item.name" :reload="reloadKey" />
        </div>
      </div>
    </div>

    <Dialog v-model:open="editOpen" title="Edit proposal" size="xl"
      :actions="[{ label: 'Save', onClick: () => saveEdit(false) }, { label: 'Save and accept', variant: 'solid', onClick: () => saveEdit(true) }]">
      <div v-if="editing" class="flex flex-col gap-3">
        <template v-for="(spec, field) in editFields" :key="field">
          <FormControl v-if="spec.type === 'markdown'" v-model="draft[field]" type="textarea" :rows="5" :label="fieldLabel(field)" :required="spec.required" :description="spec.help" />
          <FormControl v-else-if="spec.type === 'select'" v-model="draft[field]" type="select" :options="spec.options.map((o) => ({ label: o || '—', value: o }))"
            :label="fieldLabel(field)" :required="spec.required" :description="spec.help" />
          <FormControl v-else-if="spec.type === 'link'" type="select" :model-value="draft[field] ?? ''" :options="[{ label: '—', value: '' }, ...linkOptions(spec.doctype)]"
            :label="fieldLabel(field)" :required="spec.required" :description="spec.help" @update:model-value="(v) => (draft[field] = v || undefined)" />
          <DatePicker v-else-if="spec.type === 'date'" :model-value="draft[field] || ''" clearable :label="fieldLabel(field)" :required="spec.required" :description="spec.help"
            @update:model-value="(v) => (draft[field] = v)" />
          <DateTimePicker v-else-if="spec.type === 'datetime'" :model-value="draft[field] || ''" clearable :label="fieldLabel(field)" :required="spec.required" :description="spec.help"
            @update:model-value="(v) => (draft[field] = v)" />
          <FormControl v-else-if="spec.type === 'int'" type="number" :model-value="draft[field]" :label="fieldLabel(field)" :required="spec.required" :description="spec.help"
            @update:model-value="(v) => (draft[field] = v === '' || v === null ? '' : Number(v))" />
          <Checkbox v-else-if="spec.type === 'bool'" :model-value="!!Number(draft[field])" :label="fieldLabel(field)" :description="spec.help" @update:model-value="(v) => (draft[field] = v ? 1 : 0)" />
          <FormControl v-else-if="spec.type === 'scores'" v-model="draft[field]" type="textarea" class="font-mono" :rows="6" :label="fieldLabel(field)" :required="spec.required" :description="spec.help" />
          <FormControl v-else v-model="draft[field]" type="text" :maxlength="spec.max_length" :label="fieldLabel(field)" :required="spec.required" :description="spec.help" />
        </template>
      </div>
    </Dialog>
  </template>
  <div v-else-if="missing && page" class="page-body"><Card><Empty title="This item was not found." hint="It may be in another space, or it was removed." /></Card></div>
</template>
<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Alert, Avatar, Badge, Button, Checkbox, DatePicker, DateTimePicker, Dialog, FormControl, Textarea, toast } from 'frappe-ui'
import PageHead from './PageHead.vue'
import Card from './ui/Card.vue'
import SectionHead from './ui/SectionHead.vue'
import Md from './Md.vue'
import Pick from './Pick.vue'
import Empty from './Empty.vue'
import Backlinks from './Backlinks.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { refreshCounts, store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { fileKind, fileSize } from '@/lib/upload'
import { openRoute, recordChanged } from '@/lib/pane'

// The review of one inbox item. It is the full page at /inbox/:id/review and the content of the record pane.
const props = defineProps({ id: String, name: String, type: String, page: Boolean })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const route = useRoute()
const itemName = computed(() => props.id || props.name)
const proposalsHead = ref(null)
const KIND_LABEL = { 'Week Tick': 'Week tick', 'Journal Page': 'Journal page', 'Vault Document': 'Document', 'Important Date': 'Date', 'Month Goal': 'Month goal', 'Habit Log': 'Habit', 'Check-in': 'Check-in' }

const item = ref(null)
const missing = ref(false)
const schema = ref({})
const zoom = ref(false)
const dueFor = ref('')
const editingTranscript = ref(false)
const transcriptDraft = ref('')
const editOpen = ref(false)
const editing = ref(null)
const draft = ref({})
const reloadKey = ref(0)

const ctx = computed(() => item.value?.context || { areas: [], projects: [], tags: [], goals: [], people: [], habits: [], dimensions: [] })
const canRestore = computed(() => store.spaces.find((s) => s.name === item.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !item.value?.is_archived)
const pending = computed(() => item.value.proposals.filter((p) => p.status === 'Pending'))
const pct = (c) => Math.round((c || 0) * 100)
const countsLine = computed(() => {
  const by = (s) => item.value.proposals.filter((p) => p.status === s).length
  return [[by('Pending'), 'pending'], [by('Accepted'), 'accepted'], [by('Rejected'), 'rejected']].filter(([n]) => n).map(([n, l]) => `${n} ${l}`).join(', ')
})
// the line under the title: when it came in, the instruction, and the person or agent who handled it
const headParts = computed(() => {
  const it = item.value
  const parts = [`${it.source_type === 'Upload' ? 'Uploaded' : 'Received'} ${dateTime(it.received_on)}`]
  if (it.instruction) parts.push(`instruction: "${it.instruction}"`)
  const out = { text: parts.join(' · '), verb: '', who: '' }
  if (it.processed_by && it.status !== 'New') Object.assign(out, { verb: 'processed by', who: it.processed_by })
  else if (it.filed_by) Object.assign(out, { verb: 'filed by', who: it.filed_by })
  return out
})
const headSub = computed(() => [headParts.value.text, headParts.value.who && `${headParts.value.verb} ${headParts.value.who}`].filter(Boolean).join(' · '))

const areaOptions = computed(() => ctx.value.areas.map((a) => ({ value: a.name, label: (a.parent_area ? areaName(a.parent_area) + ' / ' : '') + a.area_name })))
const areaName = (id) => ctx.value.areas.find((a) => a.name === id)?.area_name || id
const goalTitle = (id) => ctx.value.goals.find((g) => g.name === id)?.title || id
const tagKey = (t) => (typeof t === 'string' ? t : 'new:' + t.new)
const tagName = (t) => (typeof t === 'string' ? ctx.value.tags.find((x) => x.name === t)?.tag_name || t : t.new + ' (new)')
function projectOptions(p) {
  const areas = [p.payload.area, ...(p.payload.also_in || [])].filter(Boolean)
  return ctx.value.projects.filter((x) => areas.includes(x.area)).map((x) => ({ value: x.name, label: x.title }))
}
function tagOptions(p) {
  const have = (p.payload.tags || []).map(tagKey)
  return ctx.value.tags.filter((t) => !have.includes(t.name)).map((t) => ({ value: t.name, label: '#' + t.tag_name }))
}
function linkOptions(doctype) {
  const c = ctx.value
  const map = {
    'Life Area': areaOptions.value, 'Life Project': c.projects.map((x) => ({ value: x.name, label: x.title })),
    'Life Goal': c.goals.map((x) => ({ value: x.name, label: x.title })), 'Life Person': c.people.map((x) => ({ value: x.name, label: x.full_name })),
    'Life Habit': c.habits.map((x) => ({ value: x.name, label: x.title })),
  }
  return map[doctype] || []
}
function factChips(p) {
  const pl = p.payload
  const out = []
  if (p.kind === 'Week Tick') {
    const g = ctx.value.goals.find((x) => x.name === pl.goal)
    if (g?.area) out.push(areaName(g.area))
    if (pl.week) out.push('Week ' + pl.week)
    if (pl.mark_done) out.push('Finished for good')
  }
  if (p.kind === 'Habit Log') out.push(ctx.value.habits.find((h) => h.name === pl.habit)?.title || pl.habit, pl.date)
  if (p.kind === 'Check-in') out.push(pl.date, `${(pl.scores || []).length} dimensions`)
  if (p.kind === 'Event') out.push(String(pl.starts_on).slice(0, 16))
  if (p.kind === 'Important Date') out.push(`${pl.day}/${pl.month}`, pl.kind || 'Birthday')
  if (p.kind === 'Month Goal') out.push(`${pl.month}/${pl.year}`)
  if (p.kind === 'Journal Page') out.push(pl.page_date, pl.page_number ? 'pages ' + pl.page_number : '')
  if (p.kind === 'Vault Document' && pl.expiry_date) out.push('expires ' + pl.expiry_date)
  if (pl.priority) out.push('Priority ' + pl.priority)
  return out.filter(Boolean)
}

async function load() {
  try {
    const it = (item.value = await api('inbox.get', { item: itemName.value }))
    emit('meta', { title: it.title, area: it.area, area_name: it.area_name, project: it.project, project_title: it.project_title, sub: headSub.value,
      fullPage: `/inbox/${it.name}/review`, archived: !!it.is_archived, canRestore: canRestore.value })
  } catch (e) {
    missing.value = true
    emit('missing')
  }
}

// One tap on a chip saves at once; the old value comes back if the server refuses.
async function setField(p, field, value) {
  const before = JSON.parse(JSON.stringify(p.payload))
  const next = { ...p.payload, [field]: value }
  if (value === null || value === '' || (Array.isArray(value) && !value.length)) delete next[field]
  if (field === 'area' || field === 'also_in') {
    const areas = [next.area, ...(next.also_in || [])]
    const proj = ctx.value.projects.find((x) => x.name === next.project)
    if (proj && !areas.includes(proj.area)) delete next.project
    if (next.also_in) next.also_in = next.also_in.filter((a) => a !== next.area)
  }
  p.payload = next
  p.error = ''
  try {
    const res = await api('review.update_payload', { proposal: p.name, payload: next })
    p.payload = res.payload
    p.preview = res.preview
  } catch (e) {
    p.payload = before
    toast.error(errorText(e))
  }
}

async function decide(p, decision, payload) {
  const before = p.status
  p.status = decision === 'accept' ? 'Accepted' : 'Rejected'
  try {
    const res = await api('review.decide', { proposal: p.name, decision, payload })
    Object.assign(p, { created_doctype: res.created_doctype, created_name: res.created_name, route: res.route, exists: true })
    item.value.status = res.item_status
    if (res.item_status === 'Done') toast.success('All decided. This item is done.')
    refreshCounts()
    reloadKey.value++
    if (!props.page) recordChanged('inbox:' + item.value.name)
    return true
  } catch (e) {
    p.status = before
    p.error = errorText(e)
    toast.error(p.error)
    return false
  }
}

async function decideAll(decision) {
  const res = await tryCall(() => api('review.decide_all', { item: item.value.name, decision }))
  if (!res) return
  await load()
  for (const err of res.errors) {
    const p = item.value.proposals.find((x) => x.name === err.proposal)
    if (p) p.error = err.error
  }
  if (res.errors.length) toast.warning(`${res.decided.length} accepted. ${res.errors.length} still need${res.errors.length === 1 ? 's' : ''} a change.`)
  else toast.success(decision === 'accept' ? `${res.decided.length} accepted.` : `${res.decided.length} rejected.`)
  refreshCounts()
  reloadKey.value++
  if (!props.page) recordChanged('inbox:' + item.value.name)
}

async function retry() {
  if (await tryCall(() => api('inbox.retry', { item: item.value.name }), 'Sent back to the agent.')) {
    await load()
    if (!props.page) recordChanged('inbox:' + item.value.name)
  }
}
function startTranscript() {
  transcriptDraft.value = item.value.transcript_md || ''
  editingTranscript.value = true
}
async function saveTranscript() {
  const res = await tryCall(() => api('inbox.update_transcript', { item: item.value.name, transcript_md: transcriptDraft.value }), 'Transcript saved.')
  if (res) {
    item.value.transcript_md = transcriptDraft.value
    editingTranscript.value = false
  }
}

const editFields = computed(() => {
  if (!editing.value) return {}
  const fields = schema.value[editing.value.kind]?.fields || {}
  return Object.fromEntries(Object.entries(fields).filter(([, s]) => !['links', 'tags'].includes(s.type)))
})
const fieldLabel = (f) => f.replace(/_md$/, '').replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
function openEdit(p) {
  editing.value = p
  const d = { ...p.payload }
  if (d.scores) d.scores = JSON.stringify(d.scores, null, 1)
  // the date and time picker reads 'YYYY-MM-DD HH:mm:ss'
  for (const k of ['starts_on', 'ends_on']) if (d[k]) d[k] = (String(d[k]).replace('T', ' ') + (String(d[k]).length <= 10 ? ' 00:00:00' : ':00')).slice(0, 19)
  draft.value = d
  editOpen.value = true
}
async function saveEdit(accept) {
  const p = editing.value
  const next = {}
  for (const [k, v] of Object.entries(draft.value)) {
    if (v === undefined || v === null || v === '') continue
    next[k] = v
  }
  try {
    if (typeof next.scores === 'string') next.scores = JSON.parse(next.scores)
  } catch (e) {
    toast.error('Scores must be valid JSON.')
    return
  }
  for (const k of ['starts_on', 'ends_on']) if (next[k]) next[k] = String(next[k]).replace('T', ' ')
  if (accept) {
    if (await decide(p, 'accept', next)) {
      p.payload = next
      if (next.title) p.preview = next.title
      editOpen.value = false
    }
    return
  }
  const res = await tryCall(() => api('review.update_payload', { proposal: p.name, payload: next }), 'Saved.')
  if (res) {
    p.payload = res.payload
    p.preview = res.preview
    p.error = ''
    editOpen.value = false
  }
}

onMounted(async () => {
  load().then(async () => {
    // a link from "4 of 13 proposals pending" lands on the pending proposals
    if (route.query.focus !== 'pending' || !item.value) return
    await nextTick()
    const head = proposalsHead.value?.$el
    const first = head?.parentElement.querySelector('[data-proposal="Pending"]') || head
    first?.scrollIntoView({ block: 'start' })
  })
  schema.value = (await tryCall(() => api('meta.proposal_schema'))) || {}
})
</script>
