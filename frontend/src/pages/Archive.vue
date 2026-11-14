<template>
  <PageHead title="Archive" sub="Archived records by area. Nothing here is deleted." />
  <div class="bd">
    <section v-if="d && d.projects.length">
      <h2 class="sh">Projects</h2>
      <div class="cd list"><div v-for="p in d.projects" :key="p.name" class="rw" style="align-items: center">
        <div class="grow"><RouterLink class="ttl" :to="`/projects/${p.name}`">{{ p.title }}</RouterLink><div class="mt">{{ [p.area_name, p.status, p.archived_on && 'archived ' + short(p.archived_on, true)].filter(Boolean).join(' · ') }}</div></div>
        <button v-if="canWrite()" class="bt s" type="button" @click="restore('Life Project', p.name)">Restore with its records</button></div></div>
    </section>
    <section v-for="g in (d ? d.groups : [])" :key="g.area">
      <h2 class="sh">{{ g.area_name }} <span class="mt" style="font-weight: 400">{{ g.records.length }}</span></h2>
      <div class="cd list"><div v-for="r in g.records" :key="r.ref_name" class="rw" style="align-items: center">
        <div class="grow"><RouterLink class="ttl" :to="r.route">{{ r.title || 'Untitled' }}</RouterLink>
          <div class="mt">{{ [r.kind, r.project_title, r.archived_on && 'archived ' + short(r.archived_on, true), REASON[r.archive_reason]].filter(Boolean).join(' · ') }}</div></div>
        <button v-if="canWrite()" class="bt s" type="button" @click="restore(r.ref_doctype, r.ref_name)">Restore</button></div></div>
    </section>
    <div v-if="d && !d.groups.length && !d.projects.length" class="cd"><Empty title="Nothing is archived."
      hint="Done tasks, finished inbox items and quiet chats move here after the number of days in Settings. Completed projects move here at once with their records." /></div>
    <div v-if="d && d.has_more"><button class="bt s" type="button" @click="load(true)">Show more</button></div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'

const REASON = { Auto: 'by the daily job', Manual: 'by hand', Project: 'with its project' }
const d = ref(null)
const count = ref(0)
async function load(append = false) {
  const res = await tryCall(() => api('archive.list', { space: store.space, start: append ? count.value : 0, page_length: 100 }))
  if (!res) return
  if (append) {
    for (const g of res.groups) {
      const have = d.value.groups.find((x) => x.area === g.area)
      if (have) have.records.push(...g.records)
      else d.value.groups.push(g)
    }
    d.value.has_more = res.has_more
    count.value += res.count
  } else {
    d.value = res
    count.value = res.count
  }
}
async function restore(doctype, name) {
  if (await tryCall(() => api('archive.restore', { doctype, name }), 'Restored.')) load()
}
onMounted(load)
</script>
