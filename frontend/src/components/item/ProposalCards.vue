<template>
  <div class="flex flex-col gap-3">
    <Card v-for="p in shown" :key="p.name" class="flex flex-col gap-2" :tint="p.status !== 'Pending'" :data-proposal="p.status">
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
          <Badge v-if="p.payload.goal && !p.filed" size="lg" :label="'Goal: ' + goalTitle(p.payload.goal)" />
          <template v-if="p.filed">
            <Pick v-if="p.payload.goal || ctx.goals.length" :model-value="p.payload.goal || null" :options="goalOptions(ctx.goals, { empty: null })"
              prefix="Goal: " placeholder="goal" :disabled="!writable" @update:model-value="(v) => setField(p, 'goal', v)" />
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
              <DatePicker format="D MMM YYYY" class="w-36" size="sm" :model-value="p.payload.due_date || ''" clearable :disabled="!writable" aria-label="Due date"
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
    <Card v-if="!shown.length"><Empty :title="emptyTitle" :hint="emptyHint" /></Card>
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
        <DatePicker format="D MMM YYYY" v-else-if="spec.type === 'date'" :model-value="draft[field] || ''" clearable :label="fieldLabel(field)" :required="spec.required" :description="spec.help"
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
<script setup>
// The proposals of one inbox item as cards with their filing chips, Accept, Edit and Reject (issue 10: shared by the Review
// screen and the item page). `only="pending"` shows the waiting ones only. After each decision it emits `decided`.
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Checkbox, DatePicker, DateTimePicker, Dialog, FormControl, toast } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Pick from '../Pick.vue'
import Empty from '../Empty.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { refreshCounts } from '@/lib/store'
import { openRoute } from '@/lib/pane'
import { areaOptionsOf, goalOptions } from '@/lib/lookups'

const props = defineProps({ item: Object, writable: Boolean, only: String, emptyTitle: { type: String, default: 'No proposals.' }, emptyHint: String })
const emit = defineEmits(['decided'])
const KIND_LABEL = { 'Week Tick': 'Week tick', 'Journal Page': 'Journal page', 'Vault Document': 'Document', 'Important Date': 'Date', 'Month Goal': 'Month goal', 'Habit Log': 'Habit', 'Check-in': 'Check-in' }

const schema = ref({})
const dueFor = ref('')
const editOpen = ref(false)
const editing = ref(null)
const draft = ref({})

const shown = computed(() => (props.only === 'pending' ? props.item.proposals.filter((p) => p.status === 'Pending') : props.item.proposals))
const ctx = computed(() => props.item?.context || { areas: [], tags: [], goals: [], people: [], habits: [], dimensions: [] })
const pct = (c) => Math.round((c || 0) * 100)
const areaOptions = computed(() => areaOptionsOf(ctx.value.areas))
const areaName = (id) => ctx.value.areas.find((a) => a.name === id)?.area_name || id
const goalTitle = (id) => ctx.value.goals.find((g) => g.name === id)?.title || id
const tagKey = (t) => (typeof t === 'string' ? t : 'new:' + t.new)
const tagName = (t) => (typeof t === 'string' ? ctx.value.tags.find((x) => x.name === t)?.tag_name || t : t.new + ' (new)')
function tagOptions(p) {
  const have = (p.payload.tags || []).map(tagKey)
  return ctx.value.tags.filter((t) => !have.includes(t.name)).map((t) => ({ value: t.name, label: '#' + t.tag_name }))
}
function linkOptions(doctype) {
  const c = ctx.value
  const map = {
    'Life Area': areaOptions.value,
    'Life Goal': goalOptions(c.goals, { empty: null }), 'Life Person': c.people.map((x) => ({ value: x.name, label: x.full_name })),
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

// One tap on a chip saves at once; the old value comes back if the server refuses.
async function setField(p, field, value) {
  const before = JSON.parse(JSON.stringify(p.payload))
  const next = { ...p.payload, [field]: value }
  if (value === null || value === '' || (Array.isArray(value) && !value.length)) delete next[field]
  if (field === 'area' || field === 'also_in') {
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
    props.item.status = res.item_status
    if (res.item_status === 'Done') toast.success('All decided. This item is done.')
    refreshCounts()
    emit('decided', p)
    return true
  } catch (e) {
    p.status = before
    p.error = errorText(e)
    toast.error(p.error)
    return false
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
  schema.value = (await tryCall(() => api('meta.proposal_schema'))) || {}
})
</script>
