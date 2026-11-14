<template>
  <PageHead title="Chats" :sub="d ? `${d.total} AI chat${d.total === 1 ? '' : 's'} · ${long(d.from_date)} to ${long(d.to_date, true)}` : ''">
    <button class="bt s ic" type="button" aria-label="Previous week" @click="step(-7)"><Ico d="m15 6-6 6 6 6" stroke="2" /></button>
    <button class="bt s ic" type="button" aria-label="Next week" @click="step(7)"><Ico d="m9 6 6 6-6 6" stroke="2" /></button>
  </PageHead>
  <div v-if="d" class="bd">
    <div class="chips">
      <span class="mt">Group by</span>
      <button v-for="g in ['day', 'area', 'project']" :key="g" class="ch" :class="{ on: groupBy === g }" type="button" @click="setGroup(g)">{{ g[0].toUpperCase() + g.slice(1) }}</button>
      <span style="flex: 1"></span>
      <span v-for="c in d.counts_by_area" :key="c.area_name" class="pl n">{{ c.area_name }} {{ c.count }}</span>
    </div>

    <section v-if="d.open_items.length">
      <h2 class="sh">Open items this week <span class="mt" style="font-weight: 400">{{ d.open_items.length }}</span></h2>
      <div class="cd list">
        <div v-for="i in d.open_items" :key="i.row" class="rw" style="align-items: center; flex-wrap: wrap">
          <div class="grow" style="flex-basis: 220px"><div class="ttl">{{ i.text }}</div><div class="mt">{{ [i.chat_title, i.area_name].filter(Boolean).join(' · ') }}</div></div>
          <div v-if="canWrite()" class="chips"><button class="bt s" type="button" @click="makeTask(i)">Make task</button><button class="bt t" type="button" @click="closeItem(i)">Close</button></div>
        </div>
      </div>
    </section>

    <section v-for="g in d.groups" :key="g.key">
      <h2 class="sh">{{ groupBy === 'day' ? `${weekday(g.label)}, ${long(g.label)}` : g.label }} <span class="mt" style="font-weight: 400">{{ g.chats.length }}</span></h2>
      <div class="tblwrap"><div class="tblscroll"><table class="tbl">
        <thead><tr><th style="width: 26%">Chat</th><th style="width: 14%">Area</th><th>Summary</th><th style="width: 28%">Open items</th></tr></thead>
        <tbody><tr v-for="c in g.chats" :key="c.name" :id="'chat-' + c.name" :class="{ hl: c.name === route.query.open }">
          <td><a v-if="c.url" :href="c.url" target="_blank" rel="noopener noreferrer" style="font-weight: 500">{{ c.title }}</a><b v-else style="font-weight: 500">{{ c.title }}</b>
            <div class="mt">{{ [c.assistant, groupBy !== 'day' && short(c.date), c.project_title].filter(Boolean).join(' · ') }}</div></td>
          <td><RouterLink v-if="c.area" :to="`/areas/${c.area}`">{{ c.area_name }}</RouterLink></td>
          <td><Md :text="c.summary_md" style="font-size: 13.5px" /></td>
          <td><ul v-if="c.open_items.length" class="items"><li v-for="i in c.open_items" :key="i.row" :class="{ shut: i.status !== 'Open' }">{{ i.text }}
            <RouterLink v-if="i.task" :to="`/tasks?open=${i.task}`" class="mt">task</RouterLink></li></ul><span v-else class="mt">None</span></td>
        </tr></tbody>
      </table></div></div>
    </section>
    <div v-if="!d.groups.length" class="cd"><Empty title="No chats in this week." hint="Your agent logs each AI chat here with a summary and open items. Nothing needs review; open items become tasks only when you press Make task." /></div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import Ico from '@/components/Ico.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { addDays, long, short, weekday } from '@/lib/dates'

const route = useRoute()
const d = ref(null)
const groupBy = ref(localStorage.getItem('lifeos-chat-group') || 'day')
const to = ref(store.today)
async function load() {
  const res = await tryCall(() => api('chats.report', { space: store.space, from_date: addDays(to.value, -6), to_date: to.value, group_by: groupBy.value }))
  if (res) d.value = res
}
function setGroup(g) {
  groupBy.value = g
  localStorage.setItem('lifeos-chat-group', g)
  load()
}
function step(n) {
  to.value = addDays(to.value, n)
  load()
}
async function makeTask(i) {
  if (await tryCall(() => api('chats.make_task', { chat: i.chat, row: i.row }), 'Task created.')) load()
}
async function closeItem(i) {
  if (await tryCall(() => api('chats.close_item', { chat: i.chat, row: i.row }))) load()
}
onMounted(load)
</script>
<style scoped>
.items { margin: 0; padding-left: 18px; list-style: disc; }
.items li.shut { color: var(--mut); text-decoration: line-through; }
tr.hl td { background: var(--b-bg); }
</style>
