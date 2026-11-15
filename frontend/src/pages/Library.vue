<template>
  <ListView v-if="listView" ref="list" title="Library" noun="notes" :filters="FILTERS" :columns="COLUMNS" :fetch="fetchList" :row-ref="(r) => 'note:' + r.name"
    default-sort="title" empty-title="No notes yet." empty-hint="Notes hold reference material and project notes, in Markdown. Add one with New note.">
    <template #sub>Notes in {{ store.space }}</template>
    <template #actions>
      <div class="chips">
        <RouterLink class="ch" to="/library" data-view="tree">Tree</RouterLink>
        <span class="ch on" data-view="list">List</span>
      </div>
      <button v-if="canWrite()" class="bt p" type="button" @click="newOpen = true">New note</button>
    </template>
    <template #cell-title="{ row }"><div class="ttl">{{ row.title }}</div><div v-if="row.tags.length" class="mt">{{ row.tags.map((t) => '#' + t).join(' ') }}</div></template>
    <template #cell-area_name="{ row }"><RouterLink v-if="row.area" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-modified="{ row }"><span class="mt">{{ short(row.modified, true) }}</span></template>
    <template #stack="{ row }"><div class="ttl">{{ row.title }}</div>
      <div class="mt">{{ [row.area_name, row.project_title, 'edited ' + short(row.modified, true), ...row.tags.map((t) => '#' + t)].filter(Boolean).join(' · ') }}</div></template>
  </ListView>
  <template v-else>
  <PageHead title="Library">
    <template #sub><RouterLink class="num" :to="{ path: '/library', query: { view: 'list' } }" data-door="library-notes">{{ notes.length }} note{{ notes.length === 1 ? '' : 's' }}</RouterLink> in {{ store.space }}</template>
    <div class="chips">
      <span class="ch on" data-view="tree">Tree</span>
      <RouterLink class="ch" :to="{ path: '/library', query: { view: 'list' } }" data-view="list">List</RouterLink>
    </div>
    <button v-if="canWrite()" class="bt p" type="button" @click="newOpen = true">New note</button>
  </PageHead>
  <div class="lib">
    <aside class="tree" :class="{ offphone: !!id }">
      <input v-model="filter" class="inp" style="width: 100%; margin-bottom: 10px" placeholder="Filter notes" aria-label="Filter notes" />
      <div v-for="g in groups" :key="g.key" class="grp">
        <div class="glabel">{{ g.label }}</div>
        <template v-for="row in g.rows" :key="row.note.name">
          <RouterLink class="nt" :class="{ on: row.note.name === id }" :style="`padding-left: ${8 + row.depth * 14}px`" :to="`/library/${row.note.name}`">
            {{ row.note.title }}<span v-if="row.note.project_title && !row.depth" class="mt"> · {{ row.note.project_title }}</span>
          </RouterLink>
        </template>
      </div>
      <Empty v-if="loaded && !notes.length" title="No notes yet." hint="Notes hold reference material and project notes, in Markdown. Add one with New note." />
      <Empty v-else-if="loaded && !groups.length" title="No note matches." hint="Clear the filter to see every note." />
    </aside>

    <section class="reader" :class="{ offphone: !id }">
      <template v-if="note">
        <RouterLink class="mt only-phone" to="/library" style="display: block; margin-bottom: 8px">← All notes</RouterLink>
        <div class="rhead">
          <div style="min-width: 0; flex: 1">
            <input v-if="editing" v-model="note.title" class="inp ttl" aria-label="Title" @input="queue" />
            <h2 v-else class="rtitle">{{ note.title }}</h2>
            <div class="mt">{{ [note.area_name, note.project_title, note.parent_title && 'under ' + note.parent_title, 'edited ' + short(note.modified, true)].filter(Boolean).join(' · ') }}
              <span v-if="editing"> · {{ saveState }}</span></div>
          </div>
          <div v-if="writable" style="display: flex; gap: 8px">
            <button v-if="editing" class="bt s" type="button" @click="preview = !preview">{{ preview ? 'Hide preview' : 'Preview' }}</button>
            <button class="bt" :class="editing ? 'p' : 's'" type="button" @click="toggleEdit">{{ editing ? 'Done' : 'Edit' }}</button>
            <Dropdown :options="noteMenu"><button class="bt s ic" type="button" aria-label="More">⋯</button></Dropdown>
          </div>
        </div>
        <div v-if="editing" class="chips" style="margin: 10px 0">
          <Pick :model-value="note.area" :options="areaOptions()" placeholder="area" @update:model-value="(v) => saveMeta({ area: v || '' })" />
          <Pick :model-value="note.project" :options="projectOptions" prefix="Project: " placeholder="project" @update:model-value="(v) => saveMeta({ project: v || '' })" />
          <Pick :model-value="note.parent_note" :options="parentOptions" prefix="Under: " placeholder="parent note" @update:model-value="(v) => saveMeta({ parent_note: v || '' })" />
          <span v-for="a in note.also_in" :key="a" class="ch sm">also in {{ areaName(a) }} <a href="#" aria-label="Remove" @click.prevent="saveMeta({ also_in: note.also_in.filter((x) => x !== a) })">×</a></span>
          <Pick :model-value="null" :options="areaOptions().filter((o) => o.value !== note.area && !note.also_in.includes(o.value))" placeholder="also in" :clearable="false"
            @update:model-value="(v) => saveMeta({ also_in: [...note.also_in, v] })" />
        </div>
        <div v-if="editing" class="editwrap" :class="{ split: preview }">
          <MdEditor v-model="note.content_md" :space="note.space" @update:model-value="queue" />
          <div v-if="preview" class="cd pv"><Md :text="note.content_md" :links="note.links" read /></div>
        </div>
        <template v-else>
          <Md v-if="note.content_md" :text="note.content_md" :links="note.links" read style="margin-top: 16px" />
          <Empty v-else title="This note is empty." hint="Use Edit to write. Type [[ to link another record." />
          <div v-if="note.children.length" style="margin-top: 24px"><h2 class="sh">Notes under this one</h2>
            <div class="cd list"><div v-for="c in note.children" :key="c.name" class="rw rowlink" @click="openRef('note:' + c.name)"><div class="ttl">{{ c.title }}</div></div></div></div>
          <div style="margin-top: 24px"><Backlinks doctype="Life Note" :name="note.name" :reload="reloadKey" /></div>
        </template>
      </template>
      <div v-else-if="missing" class="cd"><Empty title="This note was not found." hint="It may be in another space, or it was removed." /></div>
      <div v-else-if="!id" class="cd only-desktop"><Empty title="Pick a note." hint="Notes are listed on the left under their area. A note with no project is reference material for its area." /></div>
    </section>
  </div>
  </template>
  <NewRecord v-model="newOpen" title="New note" action="Create note" :fields="NEW_FIELDS" :save="create" />
  <Dialog v-model="versionsOpen" title="Earlier versions" size="xl">
    <div v-for="v in versions" :key="v.name" class="rw" style="align-items: center">
      <div class="grow"><div class="ttl">{{ v.on }}</div><div class="mt">Changed: {{ v.changed.join(', ') || 'details' }} · by {{ v.by }}</div></div>
      <button v-if="v.previous_content != null" class="bt s" type="button" @click="restore(v)">Restore the text from before this change</button>
    </div>
    <Empty v-if="!versions.length" title="No earlier versions." hint="Each save after the first keeps the previous text here." />
  </Dialog>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dialog, Dropdown } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import ListView from '@/components/ListView.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import MdEditor from '@/components/MdEditor.vue'
import Pick from '@/components/Pick.vue'
import Backlinks from '@/components/Backlinks.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaName, areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const props = defineProps({ id: String })
const route = useRoute()
// the list view sits beside the tree: /library?view=list, with its filters in the URL
const listView = computed(() => !props.id && route.query.view === 'list')
const list = ref(null)
const FILTERS = computed(() => [
  { key: 'area', label: 'Area', all: 'All areas', options: [...areaOptions(), { value: 'none', label: 'No area' }] },
  { key: 'project', label: 'Project', all: 'All projects', options: [...lookups.projects.map((p) => ({ value: p.name, label: p.title })), { value: 'none', label: 'No project (reference notes)' }] },
  { key: 'tag', label: 'Tag', all: 'All tags', options: lookups.tags.map((t) => ({ value: t.name, label: '#' + t.tag_name })) },
  { key: 'archived', label: 'Include archived', type: 'check', quiet: true },
])
const COLUMNS = [{ key: 'title', label: 'Note', width: 'minmax(200px, 2fr)', sort: 'title' }, { key: 'area_name', label: 'Area' }, { key: 'project_title', label: 'Project' },
  { key: 'modified', label: 'Edited', width: '110px', sort: 'modified' }]
async function fetchList({ filters: f, sort, dir, start, page_length }) {
  const res = await api('library.list', { space: store.space, area: f.area || undefined, project: f.project || undefined, tag: f.tag || undefined,
    include_archived: f.archived ? 1 : 0, sort: sort || undefined, dir: dir || undefined, start, page_length })
  return { rows: res.notes, total: res.total }
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

// The tree: notes under their area, then under their parent note.
const groups = computed(() => {
  const q = filter.value.trim().toLowerCase()
  const list = q ? notes.value.filter((n) => n.title.toLowerCase().includes(q)) : notes.value
  const names = new Set(list.map((n) => n.name))
  const kids = {}
  for (const n of list) if (n.parent_note && names.has(n.parent_note)) (kids[n.parent_note] = kids[n.parent_note] || []).push(n)
  const walk = (n, depth, out) => { out.push({ note: n, depth }); for (const c of kids[n.name] || []) walk(c, depth + 1, out) }
  const roots = list.filter((n) => !(n.parent_note && names.has(n.parent_note)))
  const label = (id) => { const a = areas.value.find((x) => x.name === id); if (!a) return 'Unfiled'; const p = areas.value.find((x) => x.name === a.parent_area); return (p ? p.area_name + ' / ' : '') + a.area_name }
  const by = {}
  for (const n of roots) (by[n.area || ''] = by[n.area || ''] || []).push(n)
  return Object.entries(by).map(([key, rs]) => { const rows = []; rs.forEach((r) => walk(r, 0, rows)); return { key, label: label(key), rows } })
    .sort((a, b) => (a.key === '' ? 1 : b.key === '' ? -1 : a.label.localeCompare(b.label)))
})

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
  { label: 'Earlier versions', onClick: async () => { versions.value = (await tryCall(() => api('library.versions', { note: note.value.name }))) || []; versionsOpen.value = true } },
  { label: note.value?.is_archived ? 'Restore from archive' : 'Archive', onClick: async () => {
    if (await tryCall(() => api('archive.set', { doctype: 'Life Note', name: note.value.name, archived: note.value.is_archived ? 0 : 1 }), note.value.is_archived ? 'Restored.' : 'Archived.')) { await loadTree(); router.push('/library') } } },
  { label: 'Delete', onClick: async () => {
    if (!window.confirm('Delete this note for good?')) return
    if ((await tryCall(() => db.delete('Life Note', note.value.name), 'Deleted.')) !== undefined) { await loadTree(); router.push('/library') } } },
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
<style scoped>
.lib { display: flex; flex: 1; min-height: 0; }
.tree { width: 300px; flex: none; border-right: 1px solid var(--outline-gray-1); padding: 16px 12px 40px; overflow-y: auto; }
.reader { flex: 1; min-width: 0; padding: 24px 28px 48px; }
.grp { margin-bottom: 14px; }
.glabel { font-size: 12px; font-weight: 600; color: var(--ink-gray-7); padding: 4px 8px; }
.nt { display: block; padding: 5px 8px; border-radius: 6px; color: var(--ink-gray-8); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nt:hover { background: var(--surface-gray-2); color: var(--ink-gray-9); }
.nt.on { background: var(--surface-gray-2); color: var(--ink-gray-9); font-weight: 500; }
.rhead { display: flex; gap: 12px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.rtitle { font-size: 24px; font-weight: 600; margin: 0; line-height: 1.25; font-family: var(--read); }
.inp.ttl { width: 100%; font-size: 18px; font-weight: 600; height: 40px; }
.editwrap { display: grid; grid-template-columns: 1fr; gap: 16px; }
.editwrap.split { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.pv { overflow: auto; }
@media (max-width: 800px) {
  .lib { display: block; }
  .tree { width: auto; border-right: 0; padding: 16px; }
  .reader { padding: 16px; }
  .offphone { display: none; }
  .editwrap.split { grid-template-columns: 1fr; }
  .nt { padding: 10px 8px; }
}
</style>
