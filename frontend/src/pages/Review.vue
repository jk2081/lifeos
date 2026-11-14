<template>
  <template v-if="item">
    <PageHead :title="item.title" :crumb="{ to: '/inbox', label: 'Inbox', here: item.source_type }">
      <template #sub>{{ headSub }}</template>
      <template v-if="pending.length && writable">
        <button class="bt s" type="button" @click="decideAll('reject')">Reject all</button>
        <button class="bt p" type="button" @click="decideAll('accept')">Accept all {{ pending.length }} pending</button>
      </template>
      <button v-else-if="item.status === 'Failed' && writable" class="bt p" type="button" @click="retry">Retry</button>
    </PageHead>

    <div class="bd">
      <div v-if="item.status === 'Failed'" class="cd" style="background: var(--r-bg); color: var(--r-ink); border-color: transparent">
        <b>Processing failed.</b> {{ item.error }}
      </div>
      <div v-else-if="item.status === 'New' || item.status === 'Processing'" class="cd" style="background: var(--soft)">
        <b>{{ item.status === 'New' ? 'Waiting for an agent.' : 'An agent is processing this.' }}</b>
        <span class="mt"> The summary and proposals show here when it is done.</span>
      </div>
      <div class="cols">
        <div class="half">
          <section>
            <h2 class="sh">Original</h2>
            <div v-if="!item.files.length && !item.raw_text" class="orig-empty"><span>No file was attached.</span></div>
            <div v-for="f in item.files" :key="f.file_url" class="orig">
              <template v-if="fileKind(f.file_name) === 'image'">
                <div class="imgwrap" :class="{ zoom }" @click="zoom = !zoom">
                  <img :src="item.files.length === 1 && item.preview_image ? item.preview_image : f.file_url" :alt="f.file_name" />
                </div>
              </template>
              <audio v-else-if="fileKind(f.file_name) === 'audio'" :src="f.file_url" controls style="width: 100%"></audio>
              <object v-else-if="fileKind(f.file_name) === 'pdf'" :data="f.file_url" type="application/pdf" class="pdf">
                <a :href="f.file_url" target="_blank" rel="noopener">Open {{ f.file_name }}</a>
              </object>
              <div class="mt" style="margin-top: 6px">
                <a :href="f.file_url" target="_blank" rel="noopener">{{ f.file_name }}</a> · {{ fileSize(f.file_size) }}
                <span v-if="fileKind(f.file_name) === 'image'"> · click the image to zoom</span>
              </div>
            </div>
            <div v-if="item.raw_text" class="cd" style="margin-top: 8px"><Md :text="item.raw_text" /></div>
          </section>
          <section v-if="item.transcript_md || editingTranscript">
            <h2 class="sh">Transcript
              <a v-if="writable && !editingTranscript" href="#" class="more" @click.prevent="startTranscript">Edit</a>
            </h2>
            <div class="cd">
              <template v-if="editingTranscript">
                <textarea v-model="transcriptDraft" class="inp" rows="12" style="width: 100%"></textarea>
                <div style="display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end">
                  <button class="bt s" type="button" @click="editingTranscript = false">Cancel</button>
                  <button class="bt p" type="button" @click="saveTranscript">Save transcript</button>
                </div>
              </template>
              <Md v-else :text="item.transcript_md" />
            </div>
            <p v-if="(item.transcript_md || '').includes('[?]')" class="mt" style="margin: 8px 0 0">Words marked [?] were hard to read. Edit the transcript to correct them.</p>
          </section>
        </div>

        <div class="half">
          <section v-if="item.summary_md">
            <h2 class="sh">Summary</h2>
            <div class="cd"><Md :text="item.summary_md" /></div>
          </section>
          <section>
            <h2 class="sh">Proposals<template v-if="item.proposals.length"> · {{ countsLine }}</template></h2>
            <div style="display: flex; flex-direction: column; gap: 12px">
              <div v-for="p in item.proposals" :key="p.name" class="pr" :class="{ done: p.status !== 'Pending' }">
                <div style="display: flex; align-items: flex-start; gap: 8px">
                  <span class="pl" :class="p.kind === 'Task' ? 'b' : 'n'">{{ KIND_LABEL[p.kind] || p.kind }}</span>
                  <div class="ttl" style="flex: 1; min-width: 0; font-weight: 500; overflow-wrap: anywhere">{{ p.preview }}</div>
                  <span v-if="p.status === 'Accepted'" class="pl g">Accepted</span>
                  <span v-else-if="p.status === 'Rejected'" class="pl n">Rejected</span>
                  <span v-else-if="p.confidence < 0.6" class="pl o">{{ pct(p.confidence) }}% sure</span>
                  <span v-else class="mt" style="white-space: nowrap">{{ pct(p.confidence) }}% sure</span>
                </div>
                <template v-if="p.status === 'Pending'">
                  <div v-if="p.confidence < 0.6 || p.error" class="mt" :style="p.error ? 'color: var(--r-ink)' : ''">
                    {{ p.error || 'The agent was not sure about this one. Edit it or reject it.' }}
                  </div>
                  <div class="chips">
                    <template v-if="p.filed || p.kind === 'Month Goal'">
                      <Pick :model-value="p.payload.area || null" :options="areaOptions" placeholder="area" :disabled="!writable"
                        @update:model-value="(v) => setField(p, 'area', v)" />
                    </template>
                    <span v-if="p.payload.goal" class="ch sm" style="cursor: default">Goal: {{ goalTitle(p.payload.goal) }}</span>
                    <template v-if="p.filed">
                      <Pick v-if="p.payload.project || projectOptions(p).length" :model-value="p.payload.project || null" :options="projectOptions(p)"
                        prefix="Project: " placeholder="project" :disabled="!writable" @update:model-value="(v) => setField(p, 'project', v)" />
                      <span v-for="a in p.payload.also_in || []" :key="a" class="ch sm">also in {{ areaName(a) }}
                        <a v-if="writable" href="#" aria-label="Remove" @click.prevent="setField(p, 'also_in', p.payload.also_in.filter((x) => x !== a))">×</a></span>
                      <Pick :model-value="null" :options="areaOptions.filter((o) => o.value !== p.payload.area && !(p.payload.also_in || []).includes(o.value))"
                        placeholder="also in" :clearable="false" :disabled="!writable" @update:model-value="(v) => setField(p, 'also_in', [...(p.payload.also_in || []), v])" />
                      <span v-for="t in p.payload.tags || []" :key="tagKey(t)" class="ch sm">#{{ tagName(t) }}
                        <a v-if="writable" href="#" aria-label="Remove" @click.prevent="setField(p, 'tags', p.payload.tags.filter((x) => tagKey(x) !== tagKey(t)))">×</a></span>
                      <Pick :model-value="null" :options="tagOptions(p)" placeholder="tag" :clearable="false" :disabled="!writable"
                        @update:model-value="(v) => setField(p, 'tags', [...(p.payload.tags || []), v])" />
                    </template>
                    <template v-if="p.kind === 'Task'">
                      <label v-if="p.payload.due_date || dueFor === p.name" class="ch sm">due
                        <input type="date" class="dateinp" :value="p.payload.due_date" :disabled="!writable" @change="(e) => setField(p, 'due_date', e.target.value || null)" /></label>
                      <button v-else class="ch sm add" type="button" :disabled="!writable" @click="dueFor = p.name">+ due date</button>
                    </template>
                    <span v-for="c in factChips(p)" :key="c" class="ch sm" style="cursor: default">{{ c }}</span>
                  </div>
                  <div v-if="writable" style="display: flex; gap: 8px; justify-content: flex-end; align-items: center">
                    <button class="bt t" type="button" @click="decide(p, 'reject')">Reject</button>
                    <button class="bt s" type="button" @click="openEdit(p)">Edit</button>
                    <button class="bt p" type="button" @click="decide(p, 'accept')">Accept</button>
                  </div>
                </template>
                <div v-else-if="p.status === 'Accepted'" class="mt">
                  Filed as {{ (p.created_doctype || '').replace('Life ', '').toLowerCase() }}.
                  <RouterLink v-if="p.route && p.exists" :to="p.route" style="text-decoration: underline">Open</RouterLink>
                </div>
              </div>
              <div v-if="!item.proposals.length" class="cd"><Empty title="No proposals."
                :hint="item.status === 'To Review' || item.status === 'Done' ? 'The agent found nothing to file from this item.' : 'Proposals appear here once an agent has processed the item.'" /></div>
            </div>
            <p class="mt" style="margin: 12px 0 0">Nothing here becomes a record until you accept it. The original is always kept.</p>
          </section>
          <Backlinks doctype="Life Inbox Item" :name="item.name" :reload="reloadKey" />
        </div>
      </div>
    </div>

    <Dialog v-model="editOpen" title="Edit proposal" size="xl">
        <div v-if="editing" style="display: flex; flex-direction: column; gap: 12px">
          <div v-for="(spec, field) in editFields" :key="field" class="field">
            <label class="lbl" :for="'f-' + field">{{ fieldLabel(field) }}<span v-if="spec.required"> *</span></label>
            <textarea v-if="spec.type === 'markdown'" :id="'f-' + field" v-model="draft[field]" class="inp" rows="5"></textarea>
            <select v-else-if="spec.type === 'select'" :id="'f-' + field" v-model="draft[field]" class="inp">
              <option v-for="o in spec.options" :key="o" :value="o">{{ o || '—' }}</option>
            </select>
            <select v-else-if="spec.type === 'link'" :id="'f-' + field" v-model="draft[field]" class="inp">
              <option :value="undefined">—</option>
              <option v-for="o in linkOptions(spec.doctype)" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <input v-else-if="spec.type === 'date'" :id="'f-' + field" v-model="draft[field]" type="date" class="inp" />
            <input v-else-if="spec.type === 'datetime'" :id="'f-' + field" v-model="draft[field]" type="datetime-local" class="inp" />
            <input v-else-if="spec.type === 'int'" :id="'f-' + field" v-model.number="draft[field]" type="number" class="inp" />
            <label v-else-if="spec.type === 'bool'" style="display: flex; gap: 8px; align-items: center"><input v-model="draft[field]" type="checkbox" class="ck" :true-value="1" :false-value="0" /> Yes</label>
            <textarea v-else-if="spec.type === 'scores'" :id="'f-' + field" v-model="draft[field]" class="inp" rows="6" style="font-family: monospace; font-size: 12.5px"></textarea>
            <input v-else :id="'f-' + field" v-model="draft[field]" class="inp" :maxlength="spec.max_length" />
            <div v-if="spec.help" class="mt" style="margin-top: 2px">{{ spec.help }}</div>
          </div>
        </div>
      <template #actions>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="bt s" type="button" @click="saveEdit(false)">Save</button>
          <button class="bt p" type="button" @click="saveEdit(true)">Save and accept</button>
        </div>
      </template>
    </Dialog>
  </template>
  <div v-else-if="missing" class="bd"><div class="cd"><Empty title="This item was not found." hint="It may be in another space, or it was removed." /></div></div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Dialog, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Md from '@/components/Md.vue'
import Pick from '@/components/Pick.vue'
import Empty from '@/components/Empty.vue'
import Backlinks from '@/components/Backlinks.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { refreshCounts, store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { fileKind, fileSize } from '@/lib/upload'

const props = defineProps({ id: String })
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
const writable = computed(() => store.spaces.find((s) => s.name === item.value?.space)?.access === 'Write')
const pending = computed(() => item.value.proposals.filter((p) => p.status === 'Pending'))
const pct = (c) => Math.round((c || 0) * 100)
const countsLine = computed(() => {
  const by = (s) => item.value.proposals.filter((p) => p.status === s).length
  return [[by('Pending'), 'pending'], [by('Accepted'), 'accepted'], [by('Rejected'), 'rejected']].filter(([n]) => n).map(([n, l]) => `${n} ${l}`).join(', ')
})
const headSub = computed(() => {
  const it = item.value
  const parts = [`${it.source_type === 'Upload' ? 'Uploaded' : 'Received'} ${dateTime(it.received_on)}`]
  if (it.instruction) parts.push(`instruction: "${it.instruction}"`)
  if (it.processed_by && it.status !== 'New') parts.push(`processed by ${it.processed_by}`)
  else if (it.filed_by) parts.push(`filed by ${it.filed_by}`)
  return parts.join(' · ')
})

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
    item.value = await api('inbox.get', { item: props.id })
  } catch (e) {
    missing.value = true
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
}

async function retry() {
  if (await tryCall(() => api('inbox.retry', { item: item.value.name }), 'Sent back to the agent.')) load()
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
  for (const k of ['starts_on', 'ends_on']) if (d[k]) d[k] = String(d[k]).slice(0, 16).replace(' ', 'T')
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
  load()
  schema.value = (await tryCall(() => api('meta.proposal_schema'))) || {}
})
</script>

<style scoped>
.pr { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.pr.done { background: var(--soft); }
.orig { margin-bottom: 12px; }
.orig-empty { border: 1px dashed var(--line4); border-radius: 10px; background: var(--soft); min-height: 120px; display: grid; place-items: center; color: var(--mut); }
.imgwrap { border: 1px solid var(--line); border-radius: 10px; background: var(--soft); overflow: auto; max-height: 520px; cursor: zoom-in; }
.imgwrap img { display: block; width: 100%; height: auto; }
.imgwrap.zoom { cursor: zoom-out; }
.imgwrap.zoom img { width: 220%; max-width: none; }
.pdf { width: 100%; height: 520px; border: 1px solid var(--line); border-radius: 10px; }
.dateinp { border: 0; background: transparent; color: inherit; font: inherit; padding: 0; height: 22px; }
</style>
