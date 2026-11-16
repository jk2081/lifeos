<template>
  <!-- the list: /library?view=list, on the cross-type index -->
  <NotesList v-if="listView" ref="list">
    <template #actions>
      <TabButtons model-value="list" :options="SWITCH" data-library-views />
      <Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New note" @click="newOpen = true" />
    </template>
  </NotesList>

  <!-- the tree with the reader: /library and /library/<id> -->
  <template v-else>
    <PageHead title="Notes">
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
              <Button v-else-if="node.more" variant="ghost" size="sm" class="!px-0 text-ink-gray-7" :label="node.label" data-tree-show-all @click.stop="showAll = [...showAll, node.more]" />
              <span v-else class="truncate text-sm-medium text-ink-gray-7">{{ node.label }}</span>
            </div>
          </template>
        </Tree>
        <Empty v-if="loaded && !notes.length" title="No notes yet." hint="Notes hold reference material and project notes, in Markdown. Add one with New note." />
        <Empty v-else-if="loaded && !nodes.length" title="No note matches." hint="Clear the filter to see every note." />
      </aside>

      <section class="min-w-0 flex-1 px-7 pb-12 pt-6 max-md:p-4" :class="!id && 'max-md:hidden'" data-library-reader>
        <template v-if="note">
          <div class="flex items-start gap-2">
            <Button class="-ml-2 md:hidden" variant="ghost" icon-left="lucide-arrow-left" label="All notes" route="/library" />
            <div class="flex-1" />
            <Dropdown :options="noteMenu"><Button icon="lucide-ellipsis" label="More" data-note-menu /></Dropdown>
          </div>
          <NoteEditor :key="note.name" ref="editorRef" :note="note" full :raw="raw" @saved="onSaved" />
          <div class="mx-auto w-full max-w-[720px]">
            <div v-if="note.children.length" class="mt-6"><SectionHead>Notes under this one</SectionHead>
              <Card flush><Row v-for="c in note.children" :key="c.name" :pane="'note:' + c.name" :label="c.title"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div></Row></Card></div>
            <div class="mt-6"><Backlinks doctype="Life Note" :name="note.name" :reload="reloadKey" /></div>
          </div>
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
import { Button, Dialog, Dropdown, TabButtons, TextInput, Tree, dialog, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import NotesList from '@/components/lists/NotesList.vue'
import { NOTES_VIEWS } from '@/lib/nav'
import Empty from '@/components/Empty.vue'
import NoteEditor from '@/components/NoteEditor.vue'
import Backlinks from '@/components/Backlinks.vue'
import NewRecord from '@/components/NewRecord.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, db, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'

const props = defineProps({ id: String })
const route = useRoute()
// the list view sits beside the tree: /library?view=list, with its filters in the URL
// My notes only (the Wiki has its own screen). The List is the default view; the Tree is view=tree
const listView = computed(() => !props.id && route.query.view !== 'tree')
const list = ref(null)
// Notes has three views: Tree, List and Graph (/graph, the graph of linked records)
const SWITCH = NOTES_VIEWS
const router = useRouter()
const notes = ref([])
const areas = ref([])
const loaded = ref(false)
const filter = ref('')
const note = ref(null)
const missing = ref(false)
const raw = ref(false) // "Show Markdown" in the menu: the plain text
const editorRef = ref(null)
const newOpen = ref(false)
const versionsOpen = ref(false)
const versions = ref([])
const reloadKey = ref(0)

const writable = computed(() => store.spaces.find((s) => s.name === note.value?.space)?.access === 'Write')
const NEW_FIELDS = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'area', label: 'Area', options: areaOptions() }])

const TREE_CAP = 50
const showAll = ref([])
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
  // never more than 50 notes under one heading without a "Show all" row
  const capped = (key, list_) => (list_.length > TREE_CAP && !showAll.value.includes(key)
    ? [...list_.slice(0, TREE_CAP), { key: 'more:' + key, label: `Show all ${list_.length}`, more: key, children: [] }] : list_)
  return Object.entries(by).map(([area, rs]) => ({ key: 'area:' + area, area, label: label(area), children: capped('area:' + area, rs.map((r) => node(r, true))) }))
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
async function flush() {
  await editorRef.value?.flush()
}
async function loadNote() {
  await flush()
  note.value = null
  missing.value = false
  if (!props.id) return
  try {
    note.value = await api('library.get', { note: props.id })
    if (route.query.edit) router.replace({ query: { ...route.query, edit: undefined } }) // old links: there are no modes now
  } catch (e) {
    missing.value = true
  }
}
function onSaved(res) {
  const row = notes.value.find((x) => x.name === res.name)
  if (row && (row.title !== res.title || row.area !== res.area || row.parent_note !== res.parent_note || row.project !== res.project)) loadTree()
  reloadKey.value++
}
async function create(v) {
  const res = await api('library.save', { space: store.space, title: v.title, area: v.area || '', content_md: '' })
  await loadTree()
  router.push(`/library/${res.name}?edit=1`)
}
// Part of a note that can wait becomes an idea on the Someday list, linked back to the note
async function selectionToIdea() {
  const text = (editorRef.value?.selection?.() || '').trim()
  if (!text) return toast.info('Select the text of the idea first.')
  const [first, ...rest] = text.split('\n')
  await tryCall(() => api('someday.create_idea', { space: note.value.space, title: first.replace(/^[-*#\s]+/, '').slice(0, 140), body_md: rest.join('\n').trim() || undefined,
    area: note.value.area || undefined, source_doctype: 'Life Note', source_name: note.value.name }), 'Parked on the Someday list.')
}
const noteMenu = computed(() => [
  { label: raw.value ? 'Show formatted' : 'Show Markdown', icon: 'lucide-code', onClick: () => { raw.value = !raw.value } },
  ...(writable.value && !store.isAgent && !note.value?.is_rules ? [note.value?.collection === 'Wiki'
    ? { label: 'Keep in My notes', icon: 'lucide-lock', onClick: () => move('My notes') }
    : { label: 'Hand to the wiki', icon: 'lucide-book-open', onClick: () => move('Wiki') }] : []),
  ...(writable.value && !store.isAgent ? [{ label: 'Selection to Someday', icon: 'lucide-lightbulb', onClick: selectionToIdea }] : []),
  { label: 'Earlier versions', icon: 'lucide-history', onClick: async () => { versions.value = (await tryCall(() => api('library.versions', { note: note.value.name }))) || []; versionsOpen.value = true } },
  { label: note.value?.is_archived ? 'Restore from archive' : 'Archive', icon: note.value?.is_archived ? 'lucide-archive-restore' : 'lucide-archive', onClick: async () => {
    if (await tryCall(() => api('archive.set', { doctype: 'Life Note', name: note.value.name, archived: note.value.is_archived ? 0 : 1 }), note.value.is_archived ? 'Restored.' : 'Archived.')) { await loadTree(); router.push('/library') } } },
  { label: 'Delete', icon: 'lucide-trash-2', onClick: () => dialog.danger({
    title: 'Delete this note?', message: `“${note.value.title}” moves to the trash. Restore it from Archive, Trash, within 30 days.`,
    onConfirm: async () => {
      if ((await tryCall(() => api('trash.delete', { doctype: 'Life Note', name: note.value.name }), 'Moved to the trash.')) !== undefined) { await loadTree(); router.push('/library') }
    },
  }) },
])
async function move(to) {
  await flush()
  const res = await tryCall(() => api('wiki.move', { name: note.value.name, to }), to === 'Wiki' ? 'Handed to the wiki.' : 'Kept in My notes. Agents can no longer change it.')
  if (res) { Object.assign(note.value, await api('library.get', { note: note.value.name })); loadTree() }
}
async function restore(v) {
  await flush()
  const res = await tryCall(() => api('library.save', { note: note.value.name, content_md: v.previous_content }), 'Restored.')
  if (res) Object.assign(note.value, res)
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
