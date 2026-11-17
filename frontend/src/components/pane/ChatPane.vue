<template>
  <template v-if="c">
    <template v-if="on('summary')">
    <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"><Avatar v-if="c.assistant" size="xs" :label="c.assistant" /><span>{{ c.assistant }} · {{ long(c.date, true) }}</span>
      <a v-if="c.url" class="text-ink-blue-8 hover:underline" :href="c.url" target="_blank" rel="noopener noreferrer">Open the chat</a></div>
    <section>
      <Card><Md v-if="c.summary_md" :text="c.summary_md" /><Empty v-else title="Not summarised yet." :hint="c.transcript_md ? 'An agent writes the summary from the transcript.' : 'The agent logged this chat without one.'" data-not-summarised /></Card></section>
    </template>
    <section v-if="on('transcript')" data-chat-transcript>
      <Card><Md v-if="c.transcript_md" :text="c.transcript_md" read /><Empty v-else title="No transcript." hint="Chats logged by an agent carry a summary; imported chats carry their transcript." /></Card></section>
    <section v-if="on('made')" data-source-made>
      <Card flush>
        <Row v-for="m in made" :key="m.doctype + m.name" :pane="refOfRoute(m.route)" :label="m.title"><div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ m.title }}</div><div class="text-sm text-ink-gray-6">{{ m.kind }}</div></div></Row>
        <Empty v-if="!made.length" title="Nothing made from this chat yet." hint="Tasks made from its open items, and wiki pages that cite it, are listed here." />
      </Card></section>
    <section v-if="on('items')">
      <Card flush>
        <Row v-for="i in c.open_items" :key="i.row" class="flex-wrap !items-center" data-open-item>
          <div class="min-w-0 flex-1 basis-[200px]"><div class="break-words text-base-medium" :class="i.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ i.text }}</div>
            <div v-if="i.status !== 'Open'" class="text-sm text-ink-gray-6">{{ i.status === 'Task Created' ? 'Made into a task' : 'Closed' }}</div></div>
          <Button v-if="i.task" variant="ghost" label="Open task" @click="openRef('task:' + i.task)" />
          <div v-else-if="writable && i.status === 'Open'" class="flex flex-wrap items-center gap-2"><Button label="Make task" @click="makeTask(i)" />
            <Button variant="ghost" label="Someday" data-item-someday @click="toIdea(i)" />
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
import { openRef, refOfRoute } from '@/lib/pane'

const props = defineProps({ name: String, type: String, tab: String })
// the pane's tabs: Summary, Open items, Links
const on = (t) => !props.tab || props.tab === t
const links = ref([])
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const c = ref(null)
const made = ref([])
const canRestore = computed(() => store.spaces.find((s) => s.name === c.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !c.value?.is_archived)
async function load() {
  try {
    ;[c.value, links.value, made.value] = await Promise.all([api('chats.get', { chat: props.name }), loadBacklinks('Life Chat Log', props.name),
      api('sources.made_from', { doctype: 'Life Chat Log', name: props.name })])
    const open = c.value.open_items.filter((i) => i.status === 'Open').length
    emit('meta', { title: c.value.title, area: c.value.area, area_name: c.value.area_name, goal: c.value.goal, goal_title: c.value.goal_title,
      archived: !!c.value.is_archived, canRestore: canRestore.value, sensitive: { doctype: 'Life Chat Log', name: c.value.name, on: !!c.value.is_sensitive },
      tabs: [{ value: 'summary', label: 'Summary' }, ...(c.value.transcript_md ? [{ value: 'transcript', label: 'Transcript' }] : []),
        { value: 'items', label: 'Open items', count: open, noun: 'open items' }, { value: 'made', label: 'Made from this', count: made.value.length, noun: 'records' },
        { value: 'links', label: 'Links', count: links.value.length, noun: 'linked records' }] })
  } catch (e) {
    emit('missing')
  }
}
async function makeTask(i) {
  if (await tryCall(() => api('chats.make_task', { chat: c.value.name, row: i.row }), 'Task created.')) { await load(); emit('changed') }
}
// an open item that should not weigh on the lists becomes an idea on the Someday list, and the item is closed
async function toIdea(i) {
  if (await tryCall(() => api('someday.create_idea', { space: c.value.space, title: i.text, area: c.value.area, source_doctype: 'Life Chat Log', source_name: c.value.name }), 'Parked on the Someday list.')) {
    await closeItem(i)
  }
}
async function closeItem(i) {
  if (await tryCall(() => api('chats.close_item', { chat: c.value.name, row: i.row }))) { await load(); emit('changed') }
}
onMounted(load)
</script>
