<template>
  <template v-if="c">
    <template v-if="on('summary')">
    <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"><Avatar v-if="c.assistant" size="xs" :label="c.assistant" /><span>{{ c.assistant }} · {{ long(c.date, true) }}</span>
      <a v-if="c.url" class="text-ink-blue-8 hover:underline" :href="c.url" target="_blank" rel="noopener noreferrer">Open the chat</a></div>
    <section>
      <Card><Md v-if="c.summary_md" :text="c.summary_md" /><Empty v-else title="No summary." hint="The agent logged this chat without one." /></Card></section>
    </template>
    <section v-if="on('items')">
      <Card flush>
        <Row v-for="i in c.open_items" :key="i.row" class="flex-wrap !items-center" data-open-item>
          <div class="min-w-0 flex-1 basis-[200px]"><div class="break-words text-base-medium" :class="i.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ i.text }}</div>
            <div v-if="i.status !== 'Open'" class="text-sm text-ink-gray-6">{{ i.status === 'Task Created' ? 'Made into a task' : 'Closed' }}</div></div>
          <Button v-if="i.task" variant="ghost" label="Open task" @click="openRef('task:' + i.task)" />
          <div v-else-if="writable && i.status === 'Open'" class="flex flex-wrap items-center gap-2"><Button label="Make task" @click="makeTask(i)" />
            <Button variant="ghost" label="Close" @click="closeItem(i)" /></div>
        </Row>
        <Empty v-if="!c.open_items.length" title="No open items." hint="Nothing was left to follow up from this chat." />
      </Card></section>
    <Backlinks v-if="on('links')" tab doctype="Life Chat Log" :name="c.name" :items="links" />
  </template>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Avatar, Button } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api, tryCall } from '@/lib/api'
import { loadBacklinks } from '@/lib/links'
import { store } from '@/lib/store'
import { long } from '@/lib/dates'
import { openRef } from '@/lib/pane'

const props = defineProps({ name: String, type: String, tab: String })
// the pane's tabs: Summary, Open items, Links
const on = (t) => !props.tab || props.tab === t
const links = ref([])
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const c = ref(null)
const canRestore = computed(() => store.spaces.find((s) => s.name === c.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !c.value?.is_archived)
async function load() {
  try {
    ;[c.value, links.value] = await Promise.all([api('chats.get', { chat: props.name }), loadBacklinks('Life Chat Log', props.name)])
    const open = c.value.open_items.filter((i) => i.status === 'Open').length
    emit('meta', { title: c.value.title, area: c.value.area, area_name: c.value.area_name, project: c.value.project, project_title: c.value.project_title,
      archived: !!c.value.is_archived, canRestore: canRestore.value,
      tabs: [{ value: 'summary', label: 'Summary' }, { value: 'items', label: 'Open items', count: open, noun: 'open items' },
        { value: 'links', label: 'Links', count: links.value.length, noun: 'linked records' }] })
  } catch (e) {
    emit('missing')
  }
}
async function makeTask(i) {
  if (await tryCall(() => api('chats.make_task', { chat: c.value.name, row: i.row }), 'Task created.')) { await load(); emit('changed') }
}
async function closeItem(i) {
  if (await tryCall(() => api('chats.close_item', { chat: c.value.name, row: i.row }))) { await load(); emit('changed') }
}
onMounted(load)
</script>
