<template>
  <template v-if="c">
    <div class="chips mt"><span>{{ c.assistant }} · {{ long(c.date, true) }}</span>
      <a v-if="c.url" :href="c.url" target="_blank" rel="noopener noreferrer">Open the chat</a></div>
    <section><h2 class="sh">Summary</h2>
      <div class="cd"><Md v-if="c.summary_md" :text="c.summary_md" /><Empty v-else title="No summary." hint="The agent logged this chat without one." /></div></section>
    <section><h2 class="sh">Open items</h2>
      <div class="cd list">
        <div v-for="i in c.open_items" :key="i.row" class="rw" style="align-items: center; flex-wrap: wrap" data-open-item>
          <div class="grow" style="flex-basis: 200px"><div class="ttl" :style="i.status !== 'Open' ? 'text-decoration: line-through; color: var(--mut)' : ''">{{ i.text }}</div>
            <div v-if="i.status !== 'Open'" class="mt">{{ i.status === 'Task Created' ? 'Made into a task' : 'Closed' }}</div></div>
          <a v-if="i.task" href="#" class="bt t" @click.prevent="openRef('task:' + i.task)">Open task</a>
          <div v-else-if="writable && i.status === 'Open'" class="chips"><button class="bt s" type="button" @click="makeTask(i)">Make task</button>
            <button class="bt t" type="button" @click="closeItem(i)">Close</button></div>
        </div>
        <Empty v-if="!c.open_items.length" title="No open items." hint="Nothing was left to follow up from this chat." />
      </div></section>
    <Backlinks doctype="Life Chat Log" :name="c.name" />
  </template>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { long } from '@/lib/dates'
import { openRef } from '@/lib/pane'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const c = ref(null)
const canRestore = computed(() => store.spaces.find((s) => s.name === c.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !c.value?.is_archived)
async function load() {
  try {
    c.value = await api('chats.get', { chat: props.name })
    emit('meta', { title: c.value.title, area: c.value.area, area_name: c.value.area_name, project: c.value.project, project_title: c.value.project_title,
      archived: !!c.value.is_archived, canRestore: canRestore.value })
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
