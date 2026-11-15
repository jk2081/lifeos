<template>
  <!-- One list of Settings: areas, tags, habits or check-in dimensions. Rename in place, reorder by dragging the handle
       (Alt+Up and Alt+Down on a focused row, Move up and Move down in the row menu), nest areas one level, archive. -->
  <Card flush :data-settings-list="kind">
    <div v-for="r in shown" :key="r.name" class="group relative flex min-h-11 items-center gap-2 border-b border-outline-gray-1 px-3 py-1.5 last:border-b-0 focus-visible:focus-ring"
      :class="[r.depth ? 'pl-9' : '', over === r.name ? (where === 'under' ? 'bg-surface-gray-2' : '') : '', over === r.name && where === 'before' ? 'border-t-2 border-t-outline-gray-4' : '',
        over === r.name && where === 'after' ? '!border-b-2 !border-b-outline-gray-4' : '']"
      tabindex="0" :data-row-name="r.name" :data-depth="r.depth" :aria-label="r.title" @keydown="onKey($event, r)"
      @dragover.prevent="dragOver($event, r)" @dragleave="over = over === r.name ? null : over" @drop.prevent="drop(r)">
      <span v-if="ordered && writable" class="lucide-grip-vertical size-4 shrink-0 cursor-grab text-ink-gray-6 max-md:hidden" draggable="true" aria-hidden="true" data-drag-handle
        @dragstart="dragStart($event, r)" @dragend="dragging = over = null" />
      <div class="min-w-0 flex-1">
        <TextInput v-if="editing === r.name" ref="editBox" v-model="draft" size="sm" :aria-label="`Rename ${r.title}`" data-rename-input
          @keydown.enter.prevent="saveName(r)" @keydown.esc.prevent.stop="editing = null" @blur="editing === r.name && saveName(r)" />
        <Button v-else-if="writable" class="max-w-full !justify-start !px-1 !text-base !font-normal !text-ink-gray-9" variant="ghost" :label="r.title" :tooltip="'Rename ' + r.title" data-row-title
          @click="startRename(r)" />
        <span v-else class="break-words px-1 text-base text-ink-gray-9" data-row-title>{{ r.title }}</span>
      </div>
      <NumLink v-if="countLink(r)" class="relative shrink-0 text-sm" :to="countLink(r)" :data-row-count="r.name">{{ countText(r) }}</NumLink>
      <span v-else class="shrink-0 text-sm tabular-nums text-ink-gray-6" :data-row-count="r.name">{{ countText(r) }}</span>
      <Dropdown v-if="writable" :options="menu(r)" placement="right">
        <Button variant="ghost" icon="lucide-ellipsis" :label="`More for ${r.title}`" data-row-menu />
      </Dropdown>
    </div>
    <Empty v-if="!shown.length" :title="`No ${noun} yet.`" :hint="hint" />
  </Card>

  <Dialog v-model:open="underOpen" :title="`Move ${moving?.title || ''} under`" size="sm"
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Move', variant: 'solid', onClick: confirmUnder }]">
    <Select v-model="underTarget" :options="underOptions" aria-label="Parent area" data-under-select />
  </Dialog>
</template>
<script setup>
import { computed, nextTick, ref } from 'vue'
import { Button, Dialog, Dropdown, Select, TextInput } from 'frappe-ui'
import Card from '../ui/Card.vue'
import NumLink from '../ui/NumLink.vue'
import Empty from '../Empty.vue'

const props = defineProps({
  kind: String, // area, tag, habit, dimension
  rows: Array, // [{ name, title, parent_area, count }], active rows only, in their order
  noun: String, hint: String,
  ordered: Boolean, writable: Boolean,
  countNoun: { type: Array, default: () => ['record', 'records'] },
  link: { type: Function, default: null }, // (row) => route of the list behind the count
})
// rename(row, title), reorder(names, parent), archive(row)
const emit = defineEmits(['rename', 'reorder', 'archive'])
const editing = ref(null)
const draft = ref('')
const editBox = ref(null)
const dragging = ref(null)
const over = ref(null)
const where = ref('before')
const underOpen = ref(false)
const moving = ref(null)
const underTarget = ref('')

// areas as a tree one level deep: each top-level area followed by its sub-areas
const shown = computed(() => {
  if (props.kind !== 'area') return props.rows.map((r) => ({ ...r, depth: 0 }))
  const out = []
  const top = props.rows.filter((r) => !r.parent_area || !props.rows.some((x) => x.name === r.parent_area))
  for (const a of top) {
    out.push({ ...a, depth: 0 })
    for (const c of props.rows.filter((x) => x.parent_area === a.name)) out.push({ ...c, depth: 1 })
  }
  return out
})
const peersOf = (r) => shown.value.filter((x) => (props.kind !== 'area' ? true : (x.depth ? x.parent_area : '') === (r.depth ? r.parent_area : '')))
const hasKids = (r) => props.kind === 'area' && props.rows.some((x) => x.parent_area === r.name)
const countText = (r) => `${r.count} ${r.count === 1 ? props.countNoun[0] : props.countNoun[1]}`
const countLink = (r) => (props.link && r.count ? props.link(r) : null)

function menu(r) {
  const peers = peersOf(r)
  const i = peers.findIndex((x) => x.name === r.name)
  const items = [{ label: 'Rename', icon: 'lucide-pencil', onClick: () => startRename(r) }]
  if (props.ordered) {
    if (i > 0) items.push({ label: 'Move up', icon: 'lucide-arrow-up', onClick: () => step(r, -1) })
    if (i < peers.length - 1) items.push({ label: 'Move down', icon: 'lucide-arrow-down', onClick: () => step(r, 1) })
  }
  if (props.kind === 'area' && !hasKids(r)) items.push({ label: 'Move under…', icon: 'lucide-corner-down-right', onClick: () => askUnder(r) })
  items.push({ label: 'Archive', icon: 'lucide-archive', onClick: () => emit('archive', r) })
  return items
}

async function startRename(r) {
  if (!props.writable) return
  editing.value = r.name
  draft.value = r.title
  await nextTick()
  const el = [editBox.value].flat()[0]?.$el?.querySelector('input')
  el?.focus()
  el?.select()
}
function saveName(r) {
  const t = draft.value.trim()
  editing.value = null
  if (t && t !== r.title) emit('rename', r, t)
}

// ---- order ----
function step(r, n) {
  const peers = peersOf(r).map((x) => x.name)
  const i = peers.indexOf(r.name)
  const j = i + n
  if (i < 0 || j < 0 || j >= peers.length) return
  peers.splice(j, 0, peers.splice(i, 1)[0])
  emit('reorder', peers, props.kind === 'area' ? (r.depth ? r.parent_area : '') : undefined, r.name)
}
function onKey(e, r) {
  if (!props.writable || !props.ordered || !e.altKey || editing.value) return
  if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    e.preventDefault()
    step(r, e.key === 'ArrowUp' ? -1 : 1)
  }
}
function dragStart(e, r) {
  dragging.value = r
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', r.name)
}
// the top and bottom of a row place the dragged row before or after it; the middle of a top-level area nests it there
function dragOver(e, r) {
  if (!dragging.value || dragging.value.name === r.name) return
  const box = e.currentTarget.getBoundingClientRect()
  const y = (e.clientY - box.top) / box.height
  const canNest = props.kind === 'area' && !r.depth && !hasKids(dragging.value) && dragging.value.parent_area !== r.name
  where.value = canNest && y > 0.3 && y < 0.7 ? 'under' : y < 0.5 ? 'before' : 'after'
  over.value = r.name
}
function drop(r) {
  const d = dragging.value
  dragging.value = over.value = null
  if (!d || d.name === r.name) return
  if (where.value === 'under') {
    const kids = props.rows.filter((x) => x.parent_area === r.name).map((x) => x.name)
    return emit('reorder', [...kids, d.name], r.name, d.name)
  }
  // a top-level area with sub-areas stays at the top level
  const parent = props.kind === 'area' ? (r.depth && !hasKids(d) ? r.parent_area : '') : undefined
  const target = props.kind === 'area' && r.depth && hasKids(d) ? shown.value.find((x) => x.name === r.parent_area) : r
  const peers = shown.value.filter((x) => props.kind !== 'area' || (x.depth ? x.parent_area : '') === (parent || '')).map((x) => x.name).filter((n) => n !== d.name)
  let i = peers.indexOf(target.name)
  if (i < 0) i = peers.length
  else if (where.value === 'after' && target === r) i += 1
  peers.splice(i, 0, d.name)
  emit('reorder', peers, parent, d.name)
}

// ---- move under (areas) ----
const underOptions = computed(() => [{ label: 'Top level', value: '' },
  ...shown.value.filter((x) => !x.depth && x.name !== moving.value?.name).map((x) => ({ label: x.title, value: x.name }))])
function askUnder(r) {
  moving.value = r
  underTarget.value = r.parent_area || ''
  underOpen.value = true
}
function confirmUnder() {
  const r = moving.value
  underOpen.value = false
  if ((r.parent_area || '') === underTarget.value) return
  const kids = shown.value.filter((x) => (underTarget.value ? x.depth && x.parent_area === underTarget.value : !x.depth)).map((x) => x.name).filter((n) => n !== r.name)
  emit('reorder', [...kids, r.name], underTarget.value, r.name)
}
</script>
