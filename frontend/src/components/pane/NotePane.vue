<template>
  <template v-if="note">
    <template v-if="on('note')">
    <div v-if="writable" class="flex flex-wrap items-center gap-2"><Button label="Edit" :route="`/library/${note.name}?edit=1`" data-note-edit /></div>
    <Md v-if="note.content_md" :text="note.content_md" :links="note.links" read />
    <Empty v-else title="This note is empty." hint="Use Edit to write. Type [[ to link another record." />
    </template>
    <section v-if="on('children') && note.children.length">
      <Card flush><Row v-for="c in note.children" :key="c.name" :pane="'note:' + c.name" :label="c.title"><div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div></div></Row></Card></section>
    <Backlinks v-if="on('links')" tab doctype="Life Note" :name="note.name" :items="links" />
  </template>
</template>
<script setup>
// A note in the pane: the reader. Writing happens on the full page, reached with Edit or Open full page.
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api } from '@/lib/api'
import { loadBacklinks } from '@/lib/links'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'

const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const note = ref(null)
const links = ref([])
// the pane's tabs: Note, Notes under this one (only when there are any), Links
const on = (t) => !props.tab || props.tab === t
const canRestore = computed(() => store.spaces.find((s) => s.name === note.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !note.value?.is_archived)
onMounted(async () => {
  try {
    const [n, l] = await Promise.all([api('library.get', { note: props.name }), loadBacklinks('Life Note', props.name)])
    note.value = n
    links.value = l
    emit('meta', { title: n.title, area: n.area, area_name: n.area_name, project: n.project, project_title: n.project_title,
      sub: [n.parent_title && 'under ' + n.parent_title, 'edited ' + short(n.modified, true)].filter(Boolean).join(' · '),
      fullPage: `/library/${n.name}`, archived: !!n.is_archived, canRestore: canRestore.value,
      tabs: [{ value: 'note', label: 'Note' }, ...(n.children.length ? [{ value: 'children', label: 'Notes under this one', count: n.children.length, noun: 'notes' }] : []),
        { value: 'links', label: 'Links', count: l.length, noun: 'linked records' }] })
  } catch (e) {
    emit('missing')
  }
})
</script>
