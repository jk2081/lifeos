<template>
  <PageHead title="Timeline" sub="Everything captured, by day, newest first" :count="loaded ? total : null" />
  <div class="bd">
    <div class="chips">
      <select v-model="f.area" class="inp" aria-label="Area" @change="load()"><option value="">All areas</option>
        <option v-for="o in areaOptions()" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <select v-model="f.doctype" class="inp" aria-label="Type" @change="load()"><option value="">All types</option>
        <option v-for="(label, dt) in TYPES" :key="dt" :value="dt">{{ label }}</option></select>
      <input v-model="f.from_date" type="date" class="inp" aria-label="From" @change="load()" />
      <input v-model="f.to_date" type="date" class="inp" aria-label="To" @change="load()" />
      <label class="mt" style="display: flex; gap: 6px; align-items: center"><input v-model="f.include_archived" type="checkbox" class="ck" style="margin: 0" @change="load()" /> Include archived</label>
    </div>
    <section v-for="day in days" :key="day.date">
      <h2 class="sh">{{ weekday(day.date) }}, {{ long(day.date, true) }}</h2>
      <div class="cd list">
        <IndexRow v-for="e in day.entries" :key="e.ref_name + e.kind" :row="e">
          {{ [KIND[e.kind] || e.kind, e.area_name, e.project_title, e.filed_by && 'by ' + e.filed_by, e.is_archived ? 'archived' : ''].filter(Boolean).join(' · ') }}
          <template #pill><span class="pl" :class="PILL[e.kind] || 'n'">{{ SHORT[e.kind] || e.kind }}</span></template>
        </IndexRow>
      </div>
    </section>
    <div v-if="loaded && !days.length" class="cd"><Empty title="Nothing on the timeline yet."
      hint="Every inbox item, task, note, document, chat, journal page and check-in shows here on the day it was captured." /></div>
    <div v-if="hasMore"><button class="bt s" type="button" @click="load(true)">Show earlier</button></div>
  </div>
</template>
<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import IndexRow from '@/components/IndexRow.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { long, weekday } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { onRecordChanged, paneNav, refOf } from '@/lib/pane'

const TYPES = { 'Life Inbox Item': 'Inbox items', 'Life Task': 'Tasks', 'Life Note': 'Notes', 'Life Vault Document': 'Documents',
  'Life Chat Log': 'Chats', 'Life Journal Page': 'Journal pages', 'Life Check-in': 'Check-ins', 'Life Month Plan': 'Month plans' }
const KIND = { Inbox: 'Added to the Inbox', Task: 'Task created', 'Task Done': 'Task completed', Note: 'Note', Document: 'Vault document',
  Chat: 'AI chat', 'Journal Page': 'Journal page', 'Check-in': 'Check-in', 'Month Plan': 'Month plan' }
const SHORT = { 'Task Done': 'Done', 'Journal Page': 'Page', 'Month Plan': 'Month', Document: 'Doc' }
const PILL = { Task: 'b', 'Task Done': 'g', Inbox: 'o' }
const route = useRoute()
const router = useRouter()
const q = route.query
// the filters live in the URL, so a filtered timeline can be linked to and survives a reload
const f = reactive({ area: q.area || '', doctype: q.doctype || '', from_date: q.from || '', to_date: q.to || '', include_archived: q.archived === '1' })
const total = ref(0)
const days = ref([])
const count = ref(0)
const hasMore = ref(false)
const loaded = ref(false)

async function load(append = false) {
  if (!append) router.replace({ query: { ...route.query, area: f.area || undefined, doctype: f.doctype || undefined, from: f.from_date || undefined,
    to: f.to_date || undefined, archived: f.include_archived ? '1' : undefined } })
  const res = await tryCall(() => api('timeline.get', { space: store.space, ...f, include_archived: f.include_archived ? 1 : 0, start: append ? count.value : 0, page_length: 60 }))
  if (!res) return
  if (append) {
    for (const day of res.days) {
      const last = days.value[days.value.length - 1]
      if (last && last.date === day.date) last.entries.push(...day.entries)
      else days.value.push(day)
    }
    count.value += res.count
  } else {
    days.value = res.days
    count.value = res.count
  }
  hasMore.value = res.has_more
  total.value = res.total
  loaded.value = true
  paneNav.rows = days.value.flatMap((d) => d.entries.map((e) => refOf(e.ref_doctype, e.ref_name))).filter(Boolean)
}
onRecordChanged(() => load())
onMounted(() => {
  loadLookups()
  load()
})
</script>
