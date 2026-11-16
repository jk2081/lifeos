<template>
  <template v-if="note">
    <template v-if="on('note')">
      <NoteEditor :note="note" :readonly="!writable" @saved="(r) => $emit('changed', r)" />
      <div v-if="movable" class="flex flex-wrap gap-2"><Button size="sm" :icon-left="note.collection === 'Wiki' ? 'lucide-lock' : 'lucide-book-open'"
        :label="note.collection === 'Wiki' ? 'Keep in My notes' : 'Hand to the wiki'" data-move-collection @click="move" /></div>
    </template>
    <section v-if="on('sources')" data-wiki-sources>
      <Card flush><Row v-for="s in note.sources" :key="s.doctype + s.name" :pane="(s.doctype === 'Life Chat Log' ? 'chat:' : 'source:') + s.name" :label="s.title">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ s.title || s.name }}</div><div class="text-sm text-ink-gray-6">{{ s.doctype === 'Life Chat Log' ? 'AI chat' : 'Source' }}</div></div></Row>
        <Empty v-if="!note.sources.length" title="No sources yet." hint="A wiki page cites the sources it was written from." /></Card></section>
    <section v-if="on('history')" data-wiki-history>
      <Card flush><Row v-for="c in history" :key="c.name" :pane="'change:' + c.name" :label="c.change_type + ' by ' + c.by">
        <div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">{{ c.change_type }}{{ c.reverted ? ', undone' : '' }} · {{ c.by }}</div>
          <div class="text-sm text-ink-gray-6">{{ [dateTime(c.changed_on), c.change_note, c.source_title && 'from ' + c.source_title].filter(Boolean).join(' · ') }}</div></div></Row>
        <Empty v-if="!history.length" title="No changes yet." /></Card></section>
    <section v-if="on('children') && note.children.length">
      <Card flush><Row v-for="c in note.children" :key="c.name" :pane="'note:' + c.name" :label="c.title"><div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div></div></Row></Card></section>
    <Backlinks v-if="on('links')" tab doctype="Life Note" :name="note.name" :items="links" />
  </template>
</template>
<script setup>
// A note in the pane: the same editor as the full page (no modes: click and type), with its filing as one line.
import { computed, onMounted, ref } from 'vue'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import NoteEditor from '../NoteEditor.vue'
import Empty from '../Empty.vue'
import { Button } from 'frappe-ui'
import { dateTime } from '@/lib/dates'
import { tryCall } from '@/lib/api'
import { recordChanged } from '@/lib/pane'
import Backlinks from '../Backlinks.vue'
import { api } from '@/lib/api'
import { loadBacklinks } from '@/lib/links'
import { store } from '@/lib/store'

const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const note = ref(null)
const links = ref([])
// the pane's tabs: Note, Notes under this one (only when there are any), Links
const on = (t) => !props.tab || props.tab === t
const canRestore = computed(() => store.spaces.find((s) => s.name === note.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !note.value?.is_archived)
const movable = computed(() => writable.value && !store.isAgent && !note.value?.is_rules)
const history = ref([])
async function move() {
  const to = note.value.collection === 'Wiki' ? 'My notes' : 'Wiki'
  const res = await tryCall(() => api('wiki.move', { name: note.value.name, to }), to === 'Wiki' ? 'Handed to the wiki.' : 'Kept in My notes. Agents can no longer change it.')
  if (res) { note.value.collection = res.collection; note.value.version = res.version; recordChanged('note:' + note.value.name) }
}
onMounted(async () => {
  try {
    const [n, l] = await Promise.all([api('library.get', { note: props.name }), loadBacklinks('Life Note', props.name)])
    note.value = n
    links.value = l
    const wiki = n.collection === 'Wiki'
    if (wiki) history.value = (await api('wiki.changes', { space: n.space, note: n.name, page_length: 100 })).changes
    emit('meta', { title: n.title, kind: wiki ? 'Wiki page' : 'Note', fullPage: `/library/${n.name}`, archived: !!n.is_archived, canRestore: canRestore.value,
      tabs: wiki
        ? [{ value: 'note', label: 'Page' }, { value: 'sources', label: 'Sources', count: n.sources.length, noun: 'sources' },
          { value: 'links', label: 'Links', count: l.length, noun: 'linked records' }, { value: 'history', label: 'History', count: history.value.length, noun: 'changes' }]
        : [{ value: 'note', label: 'Note' }, ...(n.children.length ? [{ value: 'children', label: 'Notes under this one', count: n.children.length, noun: 'notes' }] : []),
          { value: 'links', label: 'Links', count: l.length, noun: 'linked records' }] })
  } catch (e) {
    emit('missing')
  }
})
</script>
