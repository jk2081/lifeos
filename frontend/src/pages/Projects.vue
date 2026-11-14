<template>
  <PageHead title="Projects" :sub="`${total} ${showDone ? '' : 'active '}project${total === 1 ? '' : 's'} across areas`">
    <label class="mt" style="display: flex; gap: 6px; align-items: center"><input v-model="showDone" type="checkbox" class="ck" style="margin: 0" @change="load" /> Show done</label>
    <button v-if="canWrite()" class="bt p" type="button" @click="newOpen = true">New project</button>
  </PageHead>
  <div class="bd">
    <section v-for="g in groups" :key="g.area">
      <h2 class="sh"><RouterLink :to="`/areas/${g.area}`" style="margin: 0; color: inherit; font-weight: 600">{{ g.area_name }}</RouterLink></h2>
      <div class="pgrid"><ProjectCard v-for="p in g.projects" :key="p.name" :p="p" /></div>
    </section>
    <div v-if="loaded && !groups.length" class="cd"><Empty title="No active projects." hint="A project lives inside one area and holds tasks, notes, documents and chats. Add one with New project." /></div>
  </div>
  <NewRecord v-model="newOpen" title="New project" action="Add project" :fields="FIELDS" :save="create" @saved="load" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { areaOptions, loadLookups } from '@/lib/lookups'

const groups = ref([])
const total = ref(0)
const loaded = ref(false)
const showDone = ref(false)
const newOpen = ref(false)
const FIELDS = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'area', label: 'Area', required: true, options: areaOptions() },
  { name: 'outcome', label: 'Outcome', type: 'textarea', help: 'What will be true when this is done.' }, { name: 'target_date', label: 'Target date', type: 'date' }])
async function load() {
  const res = await tryCall(() => api('projects.list', { space: store.space, include_done: showDone.value ? 1 : 0 }))
  if (res) {
    groups.value = res.groups
    total.value = res.total
    loaded.value = true
  }
}
async function create(v) {
  await db.insert({ doctype: 'Life Project', space: store.space, status: 'Active', ...v })
  loadLookups(true)
}
onMounted(() => {
  loadLookups()
  load()
})
</script>
<style scoped>
.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
</style>
