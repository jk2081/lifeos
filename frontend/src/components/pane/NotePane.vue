<template>
  <template v-if="note">
    <div v-if="writable" class="chips"><RouterLink class="bt s" :to="`/library/${note.name}?edit=1`" data-note-edit>Edit</RouterLink></div>
    <Md v-if="note.content_md" :text="note.content_md" :links="note.links" read />
    <Empty v-else title="This note is empty." hint="Use Edit to write. Type [[ to link another record." />
    <section v-if="note.children.length"><h2 class="sh">Notes under this one</h2>
      <div class="cd list"><div v-for="c in note.children" :key="c.name" class="rw rowlink" @click="openRef('note:' + c.name)"><div class="grow"><div class="ttl">{{ c.title }}</div></div></div></div></section>
    <Backlinks doctype="Life Note" :name="note.name" />
  </template>
</template>
<script setup>
// A note in the pane: the reader. Writing happens on the full page, reached with Edit or Open full page.
import { computed, onMounted, ref } from 'vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { openRef } from '@/lib/pane'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const note = ref(null)
const canRestore = computed(() => store.spaces.find((s) => s.name === note.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !note.value?.is_archived)
onMounted(async () => {
  try {
    const n = (note.value = await api('library.get', { note: props.name }))
    emit('meta', { title: n.title, area: n.area, area_name: n.area_name, project: n.project, project_title: n.project_title,
      sub: [n.parent_title && 'under ' + n.parent_title, 'edited ' + short(n.modified, true)].filter(Boolean).join(' · '),
      fullPage: `/library/${n.name}`, archived: !!n.is_archived, canRestore: canRestore.value })
  } catch (e) {
    emit('missing')
  }
})
</script>
