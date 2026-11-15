<template>
  <!-- the list: /library?view=list, on the cross-type index -->
  <ListView v-if="listView" ref="list" title="Library" noun="notes" screen="library" doctype="Life Index" :spec="SPEC" :flag-labels="{ archived: 'Include archived' }" :quiet="['archived']"
    :virtual="VIRTUAL" :hidden="HIDDEN" :quick="['title', 'area', 'project']" :synthetic="SYNTHETIC" :fetch="fetchList" :row-ref="(r) => 'note:' + r.name"
    empty-title="No notes yet." empty-hint="Notes hold reference material and project notes, in Markdown. Add one with New note.">
    <template #sub>Notes in {{ store.space }}</template>
    <template #actions>
      <TabButtons model-value="list" :options="SWITCH" data-library-views />
      <Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New note" @click="newOpen = true" />
    </template>
    <template #cell-title="{ row }"><span class="break-words font-medium text-ink-gray-9">{{ row.title }}</span></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-project="{ row }"><span class="truncate">{{ row.project_title }}</span></template>
    <template #cell-record_date="{ row }"><span class="whitespace-nowrap">{{ short(row.record_date || row.modified, true) }}</span></template>
    <template #cell-kind><span class="truncate">Note</span></template>
    <template #cell-_tags="{ row }"><span class="truncate text-sm text-ink-gray-6">{{ row.tags.map((t) => '#' + t).join(' ') }}</span></template>
    <template #stack="{ row }"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
      <div class="text-sm text-ink-gray-6">{{ [row.area_name, row.project_title, 'edited ' + short(row.modified, true), ...row.tags.map((t) => '#' + t)].filter(Boolean).join(' · ') }}</div></template>
  </ListView>

  <!-- the tree with the reader: /library and /library/<id> -->
  <template v-else>
    <PageHead title="Library">
      <template #sub><NumLink :to="{ path: '/library', query: { view: 'list', all: '1' } }" data-door="library-notes">{{ notes.length }} note{{ notes.length === 1 ? '' : 's' }}</NumLink> in {{ store.space }}</template>
      <TabButtons model-value="tree" :options="SWITCH" data-library-views />
      <Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New note" @click="newOpen = true" />
    </PageHead>
    <div class="flex min-h-0 flex-1 max-md:block" data-library>
      <aside class="w-[300px] flex-none overflow-y-auto border-r border-outline-gray-1 px-3 pb-10 pt-4 max-md:w-auto max-md:border-r-0 max-md:p-4" :class="id && 'max-md:hidden'" data-library-tree>
        <TextInput v-model="filter" class="mb-2.5" placeholder="Filter notes" aria-label="Filter notes">
          <template #prefix><span class="lucide-search size-4 text-ink-gray-6" aria-hidden="true" /></template>
        </TextInput>
        <Tree v-if="nodes.length" v-model:expanded="expanded" class="[--tree-indent:16px] max-md:[--tree-row-height:40px]" :nodes="nodes" node-key="key" guides="lines" aria-label="Notes">
          <template #item="{ node, expanded: open, hasChildren, toggle }">
            <!-- an area opens and closes; a note is a link to the reader, with the open note marked -->
            <div class="-mx-1.5 flex min-w-0 flex-1 items-center gap-1 self-stretch rounded-5 px-1.5" :class="node.note && node.key === id ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
              :data-note="node.note ? node.key : undefined" :data-area="node.note ? undefined : node.key" :data-active="(node.note && node.key === id) || undefined" @click.stop="!node.note && toggle()">
              <Button v-if="hasChildren" class="!size-5 shrink-0" variant="ghost" :icon="open ? 'lucide-chevron-down' : 'lucide-chevron-right'" :label="open ? 'Collapse' : 'Expand'" tabindex="-1" @click.stop="toggle()" />
              <span v-else-if="node.note" class="size-5 shrink-0" aria-hidden="true" />
              <RouterLink v-if="node.note" class="flex min-w-0 flex-1 items-center self-stretch rounded-4 text-base focus-visible:focus-ring" :class="node.key === id ? 'font-medium text-ink-gray-9' : 'text-ink-gray-8'"
                :to="`/library/${node.key}`" :aria-current="node.key === id ? 'page' : undefined">
                <span class="truncate">{{ node.label }}<span v-if="node.note.project_title && node.top" class="text-sm font-normal text-ink-gray-6"> · {{ node.note.project_title }}</span></span>
              </RouterLink>
              <span v-else class="truncate text-sm-medium text-ink-gray-7">{{ node.label }}</span>
            </div>
          </template>
        </Tree>
        <Empty v-if="loaded && !notes.length" title="No notes yet." hint="Notes hold reference material and project notes, in Markdown. Add one with New note." />
        <Empty v-else-if="loaded && !nodes.length" title="No note matches." hint="Clear the filter to see every note." />
      </aside>

      <section class="min-w-0 flex-1 px-7 pb-12 pt-6 max-md:p-4" :class="!id && 'max-md:hidden'" data-library-reader>
        <template v-if="note">
          <Button class="-ml-2 mb-2 md:hidden" variant="ghost" icon-left="lucide-arrow-left" label="All notes" route="/library" />
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <TextInput v-if="editing" v-model="note.title" size="lg" aria-label="Title" @update:model-value="queue" />
              <h2 v-else class="read !text-2xl font-semibold !leading-tight text-ink-gray-9">{{ note.title }}</h2>
              <div class="mt-1 text-sm text-ink-gray-6">{{ [note.area_name, note.project_title, note.parent_title && 'under ' + note.parent_title, 'edited ' + short(note.modified, true)].filter(Boolean).join(' · ') }}
                <span v-if="editing" data-save-state> · {{ saveState }}</span></div>
            </div>
            <div v-if="writable" class="flex gap-2">
              <Button v-if="editing" :icon-left="preview ? 'lucide-eye-off' : 'lucide-eye'" :label="preview ? 'Hide preview' : 'Preview'" @click="preview = !preview" />
              <Button :variant="editing ? 'solid' : 'subtle'" :label="editing ? 'Done' : 'Edit'" data-edit @click="toggleEdit" />
              <Dropdown :options="noteMenu"><Button icon="lucide-ellipsis" label="More" /></Dropdown>
            </div>
          </div>
          <div v-if="editing" class="my-2.5 flex flex-wrap items-center gap-2">
            <Pick :model-value="note.area" :options="areaOptions()" placeholder="area" @update:model-value="(v) => saveMeta({ area: v || '' })" />
            <Pick :model-value="note.project" :options="projectOptions" prefix="Project: " placeholder="project" @update:model-value="(v) => saveMeta({ project: v || '' })" />
            <Pick :model-value="note.parent_note" :options="parentOptions" prefix="Under: " placeholder="parent note" @update:model-value="(v) => saveMeta({ parent_note: v || '' })" />
            <Button v-for="a in note.also_in" :key="a" :label="`also in ${areaName(a)}`" icon-right="lucide-x" tooltip="Remove" @click="saveMeta({ also_in: note.also_in.filter((x) => x !== a) })" />
            <Pick :model-value="null" :options="areaOptions().filter((o) => o.value !== note.area && !note.also_in.includes(o.value))" placeholder="also in" :clearable="false"
              @update:model-value="(v) => saveMeta({ also_in: [...note.also_in, v] })" />
          </div>
          <div v-if="editing" class="grid grid-cols-1 gap-4" :class="preview && 'md:grid-cols-2'">
            <MdEditor v-model="note.content_md" class="min-w-0" :space="note.space" @update:model-value="queue" />
            <Card v-if="preview" class="min-w-0 overflow-auto"><Md :text="note.content_md" :links="note.links" read /></Card>
          </div>
          <template v-else>
            <Md v-if="note.content_md" class="mt-4" :text="note.content_md" :links="note.links" read />
            <Empty v-else title="This note is empty." hint="Use Edit to write. Type [[ to link another record." />
            <div v-if="note.children.length" class="mt-6"><SectionHead>Notes under this one</SectionHead>
              <Card flush><Row v-for="c in note.children" :key="c.name" :pane="'note:' + c.name" :label="c.title"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div></Row></Card></div>
            <div class="mt-6"><Backlinks doctype="Life Note" :name="note.name" :reload="reloadKey" /></div>
          </template>
        </template>
        <Card v-else-if="missing"><Empty title="This note was not found." hint="It may be in another space, or it was removed." /></Card>
        <Card v-else-if="!id" class="max-md:hidden"><Empty title="Pick a note." hint="Notes are listed on the left under their area. A note with no project is reference material for its area." /></Card>
      </section>
    </div>
  </template>

  <NewRecord v-model="newOpen" title="New note" action="Create note" :fields="NEW_FIELDS" :save="create" />
  <Dialog v-model:open="versionsOpen" title="Earlier versions" size="xl">
    <div data-versions>
      <Row v-for="v in versions" :key="v.name" class="!items-center">
        <div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">{{ v.on }}</div><div class="text-sm text-ink-gray-6">Changed: {{ v.changed.join(', ') || 'details' }} · by {{ v.by }}</div></div>
        <Button v-if="v.previous_content != null" label="Restore the text from before this change" @click="restore(v)" />
      </Row>
      <Empty v-if="!versions.length" title="No earlier versions." hint="Each save after the first keeps the previous text here." />
    </div>
  </Dialog>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Dialog, Dropdown, TabButtons, TextInput, Tree, dialog } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import ListView from '@/components/ListView.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import MdEditor from '@/components/MdEditor.vue'
import Pick from '@/components/Pick.vue'
import Backlinks from '@/components/Backlinks.vue'
import NewRecord from '@/components/NewRecord.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, db, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaName, areaOptions, loadLookups, lookups } from '@/lib/lookups'

const props = defineProps({ id: String })
const route = useRoute()
// the list view sits beside the tree: /library?view=list, with its filters in the URL
const listView = computed(() => !props.id && route.query.view === 'list')
const list = ref(null)
const SWITCH = [{ label: 'Tree', value: 'tree', route: '/library' }, { label: 'List', value: 'list', route: { path: '/library', query: { view: 'list' } } }]
// the short URL parameters of the list (lib/filterUrl.js)
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'project', field: 'project', kind: 'link' }, { key: 'tag', field: 'tag', kind: 'value' }, { key: 'archived', kind: 'flag' }]
const VIRTUAL = [{ fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' }, { fieldname: 'project', label: 'Project', fieldtype: 'Link', options: 'Life Project' },
  { fieldname: 'tag', label: 'Tag', fieldtype: 'Link', options: 'Life Tag' }]
const HIDDEN = ['ref_doctype', 'ref_name', 'kind', 'search_text', 'also_in_csv', 'tags_csv', 'status', 'record_owner']
const SYNTHETIC = [{ key: '_tags', label: 'Tags' }]
async function fetchList({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await api('library.list', { space: store.space, area: p.area, project: p.project, tag: p.tag, include_archived: p.archived ? 1 : 0,
    filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.notes, total: res.total }
}
const router = useRouter()
const notes = ref([])
const areas = ref([])
const loaded = ref(false)
const filter = ref('')
const note = ref(null)
const missing = ref(false)
const editing = ref(false)
const preview = ref(window.innerWidth > 1100)
const saveState = ref('Saved')
const newOpen = ref(false)
const versionsOpen = ref(false)
const versions = ref([])
const reloadKey = ref(0)
let timer = null
let dirty = false

const writable = computed(() => store.spaces.find((s) => s.name === note.value?.space)?.access === 'Write')
const NEW_FIELDS = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'area', label: 'Area', options: areaOptions() }])
const projectOptions = computed(() => lookups.projects.filter((p) => [note.value.area, ...note.value.also_in].includes(p.area)).map((p) => ({ value: p.name, label: p.title })))
const parentOptions = computed(() => notes.value.filter((n) => n.name !== note.value.name && n.parent_note !== note.value.name).map((n) => ({ value: n.name, label: n.title })))

// The tree: notes under their area, then under their parent note. An area is a node with the key 'area:<id>'; a note's key is its id.
const nodes = computed(() => {
  const q = filter.value.trim().toLowerCase()
  const shown = q ? notes.value.filter((n) => n.title.toLowerCase().includes(q)) : notes.value
  const names = new Set(shown.map((n) => n.name))
  const kids = {}
  for (const n of shown) if (n.parent_note && names.has(n.parent_note)) (kids[n.parent_note] = kids[n.parent_note] || []).push(n)
  const node = (n, top) => ({ key: n.name, label: n.title, note: n, top, children: (kids[n.name] || []).map((c) => node(c, false)) })
  const roots = shown.filter((n) => !(n.parent_note && names.has(n.parent_note)))
  const label = (id) => { const a = areas.value.find((x) => x.name === id); if (!a) return 'Unfiled'; const p = areas.value.find((x) => x.name === a.parent_area); return (p ? p.area_name + ' / ' : '') + a.area_name }
  const by = {}
  for (const n of roots) (by[n.area || ''] = by[n.area || ''] || []).push(n)
  return Object.entries(by).map(([area, rs]) => ({ key: 'area:' + area, area, label: label(area), children: rs.map((r) => node(r, true)) }))
    .sort((a, b) => (a.area === '' ? 1 : b.area === '' ? -1 : a.label.localeCompare(b.label)))
})
// Everything is open until the person closes it: a branch is opened the first time it is seen, and stays as it was left after that.
const expanded = ref([])
const seen = new Set()
watch(nodes, (list_) => {
  const fresh = []
  const walk = (n) => {
    if (!n.children.length) return
    if (!seen.has(n.key)) { seen.add(n.key); fresh.push(n.key) }
    n.children.forEach(walk)
  }
  list_.forEach(walk)
  if (fresh.length) expanded.value = [...expanded.value, ...fresh]
}, { immediate: true })

async function loadTree() {
  const res = await tryCall(() => api('library.tree', { space: store.space }))
  if (res) {
    notes.value = res.notes
    areas.value = res.areas
    loaded.value = true
  }
}
async function loadNote() {
  await flush()
  note.value = null
  missing.value = false
  editing.value = false
  if (!props.id) return
  try {
    note.value = await api('library.get', { note: props.id })
    if (route.query.edit && writable.value) editing.value = true
  } catch (e) {
    missing.value = true
  }
}
function queue() {
  dirty = true
  saveState.value = 'Typing…'
  clearTimeout(timer)
  timer = setTimeout(flush, 2000) // autosave after two seconds of no typing
}
async function flush() {
  clearTimeout(timer)
  if (!dirty || !note.value) return
  dirty = false
  saveState.value = 'Saving…'
  const n = note.value
  const res = await tryCall(() => api('library.save', { note: n.name, title: n.title, content_md: n.content_md }))
  if (res && note.value && note.value.name === res.name) {
    note.value.links = res.links
    note.value.modified = res.modified
    saveState.value = 'Saved'
    const row = notes.value.find((x) => x.name === res.name)
    if (row) row.title = res.title
  } else if (!res) saveState.value = 'Not saved'
}
async function toggleEdit() {
  if (editing.value) {
    await flush()
    reloadKey.value++
    if (route.query.edit) router.replace({ query: {} })
  } else saveState.value = 'Saved'
  editing.value = !editing.value
}
async function saveMeta(values) {
  await flush()
  const res = await tryCall(() => api('library.save', { note: note.value.name, ...values }))
  if (res) {
    Object.assign(note.value, res)
    loadTree()
  }
}
async function create(v) {
  const res = await api('library.save', { space: store.space, title: v.title, area: v.area || '', content_md: '' })
  await loadTree()
  router.push(`/library/${res.name}?edit=1`)
}
const noteMenu = computed(() => [
  { label: 'Earlier versions', icon: 'lucide-history', onClick: async () => { versions.value = (await tryCall(() => api('library.versions', { note: note.value.name }))) || []; versionsOpen.value = true } },
  { label: note.value?.is_archived ? 'Restore from archive' : 'Archive', icon: note.value?.is_archived ? 'lucide-archive-restore' : 'lucide-archive', onClick: async () => {
    if (await tryCall(() => api('archive.set', { doctype: 'Life Note', name: note.value.name, archived: note.value.is_archived ? 0 : 1 }), note.value.is_archived ? 'Restored.' : 'Archived.')) { await loadTree(); router.push('/library') } } },
  { label: 'Delete', icon: 'lucide-trash-2', onClick: () => dialog.danger({
    title: 'Delete this note for good?', message: `“${note.value.title}” will be removed. This cannot be undone.`,
    onConfirm: async () => {
      if ((await tryCall(() => db.delete('Life Note', note.value.name), 'Deleted.')) !== undefined) { await loadTree(); router.push('/library') }
    },
  }) },
])
async function restore(v) {
  note.value.content_md = v.previous_content
  dirty = true
  await flush()
  versionsOpen.value = false
}
watch(() => props.id, loadNote)
onMounted(() => {
  loadLookups()
  loadTree()
  loadNote()
})
onBeforeUnmount(flush)
</script>
