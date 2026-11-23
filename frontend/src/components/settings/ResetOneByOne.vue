<template>
  <Card class="flex flex-col gap-3" data-one-by-one>
    <template v-if="item">
      <div class="text-sm text-ink-gray-6" data-obo-position>{{ phone ? 'One by one · ' : 'Item ' }}{{ decided + 1 }} of {{ left + decided }}{{ phone ? '' : ' left' }}</div>
      <div>
        <button type="button" class="text-left text-lg-semibold text-ink-gray-9 hover:underline focus-visible:focus-ring" data-obo-title @click="openRef(item.ref)">{{ item.title }}</button>
        <div class="mt-0.5 text-sm text-ink-gray-6" data-obo-meta>{{ [item.type, item.area_name, item.goal_title, 'created ' + short(item.created), `untouched ${item.days} day${item.days === 1 ? '' : 's'}`, !item.goal_title && item.type === 'Task' ? 'no goal' : ''].filter(Boolean).join(' · ') }}</div>
      </div>
      <div v-if="item.source" class="rounded-4 bg-surface-gray-1 px-3 py-2 text-base text-ink-gray-7" data-obo-source>
        From {{ item.source.kind.toLowerCase() }} <a href="#" class="text-ink-blue-8 hover:underline" @click.prevent="openRef(item.source.ref)">“{{ item.source.title }}”</a>, {{ short(item.source.date) }}.
        <span v-if="item.source.excerpt">{{ item.source.excerpt }}</span>
      </div>
      <div v-if="writable" :class="phone ? 'grid grid-cols-2 gap-2' : 'flex flex-wrap gap-2'">
        <Button v-for="d in DECISIONS" :key="d.key" :size="phone ? 'xl' : 'md'" variant="outline" :theme="d.key === 'delete' ? 'red' : 'gray'"
          :class="phone && d.key === 'delete' ? 'col-span-2' : ''" :data-obo="d.key" :aria-keyshortcuts="d.letter" @click="choose(d.key)">
          {{ d.label }}<template v-if="!phone" #suffix><KeyboardShortcut :combo="d.letter" /></template>
        </Button>
      </div>
      <p v-if="!phone" class="text-sm text-ink-gray-6">Do asks for a date. Waiting asks for whom. Someday moves it to the Someday list with its creation date kept; it comes back for review in {{ months }} months. Deleted items stay in the trash for 30 days.</p>
    </template>
    <Empty v-else-if="loaded" title="Nothing left to decide." hint="Every open task and open-ended goal has been looked at in this session." />
    <Dialog v-model:open="ask.open" :title="ask.kind === 'do' ? 'When will you do it?' : 'Waiting on whom?'" size="sm"
      :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: ask.kind === 'do' ? 'Set date' : 'Mark waiting', variant: 'solid', onClick: confirmAsk }]">
      <DatePicker v-if="ask.kind === 'do'" v-model="ask.date" label="Date" format="D MMM YYYY" data-obo-date />
      <TextInput v-else v-model="ask.who" label="Waiting on" placeholder="A person or a thing" data-obo-who @keydown.enter="confirmAsk" />
    </Dialog>
  </Card>
</template>
<script setup>
// Reset's one by one: the oldest untouched open task or open-ended goal, where it came from, and five decisions with keys on a
// desktop (D, W, S, A, X) and large buttons on a phone. After each decision the next item shows; each can be undone
// from the toast for a minute.
import { settingsData } from '@/data/settings'
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { Button, DatePicker, Dialog, KeyboardShortcut, TextInput, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import { errorText } from '@/lib/api'
import { store } from '@/lib/store'
import { addDays, short } from '@/lib/dates'
import { openRef, recordChanged } from '@/lib/pane'

const props = defineProps({ space: String, writable: Boolean, phone: Boolean, months: { type: Number, default: 3 }, only: { type: Array, default: null }, keys: { type: Boolean, default: true } })
const emit = defineEmits(['decided'])
const DECISIONS = [{ key: 'do', label: 'Do', letter: 'D' }, { key: 'waiting', label: 'Waiting', letter: 'W' }, { key: 'someday', label: 'Someday', letter: 'S' },
  { key: 'archive', label: 'Archive', letter: 'A' }, { key: 'delete', label: 'Delete', letter: 'X' }]
const item = ref(null)
const left = ref(0)
const decided = ref(0)
const loaded = ref(false)
const skip = ref([])
const ask = reactive({ open: false, kind: '', date: '', who: '' })

async function load() {
  const res = await settingsData.reset.next_item({ space: props.space || store.space, skip: JSON.stringify(skip.value), only: props.only ? JSON.stringify(props.only) : undefined })
  item.value = res.item
  left.value = res.left
  loaded.value = true
}
function choose(kind) {
  if (!item.value) return
  if (kind === 'do' || kind === 'waiting') return Object.assign(ask, { open: true, kind, date: addDays(store.today, 7), who: '' })
  decide(kind)
}
async function confirmAsk({ close } = {}) {
  if (ask.kind === 'waiting' && !ask.who.trim()) return
  ask.open = false
  close?.()
  await decide(ask.kind, ask.kind === 'do' ? { date: ask.date } : { waiting_on: ask.who })
}
async function decide(kind, extra = {}) {
  const it = item.value
  try {
    const res = await settingsData.reset.decide({ doctype: it.doctype, name: it.name, decision: kind, ...extra })
    skip.value.push(it.name)
    decided.value++
    recordChanged(it.ref)
    emit('decided', { kind, item: it })
    toast.success(`${it.title}: ${DECISIONS.find((d) => d.key === kind).label.toLowerCase()}.`, { duration: 60000,
      action: { label: 'Undo', onClick: () => undo(res.undo, it) } })
    await load()
  } catch (e) {
    toast.error(errorText(e))
  }
}
async function undo(log, it) {
  try {
    await settingsData.reset.undo({ log: JSON.stringify(log) })
    skip.value = skip.value.filter((n) => n !== it.name)
    decided.value = Math.max(decided.value - 1, 0)
    recordChanged(it.ref)
    toast.success('Undone.')
    await load()
  } catch (e) { toast.error(errorText(e)) }
}
function onKey(e) {
  if (!props.keys || props.phone || !item.value || ask.open || e.metaKey || e.ctrlKey || e.altKey) return
  const t = e.target
  if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || (t.closest && t.closest('[role="dialog"], [data-pane], .cm-editor'))) return
  const d = DECISIONS.find((x) => x.letter.toLowerCase() === e.key.toLowerCase())
  if (d && props.writable) { e.preventDefault(); e.stopPropagation(); choose(d.key) }
}
watch(() => props.only, () => { skip.value = []; decided.value = 0; load() })
onMounted(() => { load(); window.addEventListener('keydown', onKey, true) })
onUnmounted(() => window.removeEventListener('keydown', onKey, true))
defineExpose({ reload: load, decided })
</script>
