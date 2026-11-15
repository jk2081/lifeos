<template>
  <PageHead title="Areas" :sub="`${store.space} · where records are filed`">
    <button v-if="canWrite()" class="bt p" type="button" @click="newOpen = true">New area</button>
  </PageHead>
  <div class="bd">
    <div class="grid">
      <div v-for="a in top" :key="a.name" class="cd ar" @click="(e) => !e.target.closest('a') && $router.push(`/areas/${a.name}`)">
        <RouterLink :to="`/areas/${a.name}`" style="font-weight: 600; color: var(--ink)">{{ a.area_name }}</RouterLink>
        <div class="mt"><RouterLink class="num" :to="{ path: '/projects', query: { area: a.name, status: 'Active' } }">{{ a.projects }} active project{{ a.projects === 1 ? '' : 's' }}</RouterLink> ·
          <RouterLink class="num" :to="{ path: '/tasks', query: { area: a.name, view: 'list' } }">{{ a.open_tasks }} open task{{ a.open_tasks === 1 ? '' : 's' }}</RouterLink> ·
          <RouterLink class="num" :to="{ path: '/library', query: { view: 'list', area: a.name } }">{{ a.notes }} note{{ a.notes === 1 ? '' : 's' }}</RouterLink></div>
        <div v-if="children(a).length" class="chips" style="margin-top: 6px">
          <RouterLink v-for="c in children(a)" :key="c.name" class="ch sm" :to="`/areas/${c.name}`">{{ c.area_name }}</RouterLink>
        </div>
      </div>
    </div>
    <div v-if="loaded && !top.length" class="cd"><Empty title="No areas yet." hint="Areas are your own filing headings, such as Family or Work. Add one with New area." /></div>
    <p v-if="unfiled" class="mt" style="margin: 0"><RouterLink class="num" :to="{ path: '/tasks', query: { area: 'none', view: 'list' } }">{{ unfiled }} open task{{ unfiled === 1 ? '' : 's' }}</RouterLink> {{ unfiled === 1 ? 'has' : 'have' }} no area yet. Open the list to file them.</p>
  </div>
  <NewRecord v-model="newOpen" title="New area" action="Add area" :fields="FIELDS" :save="create" @saved="load" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { loadLookups } from '@/lib/lookups'

const areas = ref([])
const unfiled = ref(0)
const loaded = ref(false)
const newOpen = ref(false)
const top = computed(() => areas.value.filter((a) => !a.parent_area))
const children = (a) => areas.value.filter((c) => c.parent_area === a.name)
const FIELDS = computed(() => [
  { name: 'area_name', label: 'Name', required: true },
  { name: 'parent_area', label: 'Inside', options: top.value.map((a) => ({ value: a.name, label: a.area_name })) },
])
async function load() {
  const res = await tryCall(() => api('area.tree', { space: store.space }))
  if (res) {
    areas.value = res.areas
    unfiled.value = res.unfiled_tasks
    loaded.value = true
  }
}
async function create(v) {
  await db.insert({ doctype: 'Life Area', space: store.space, area_name: v.area_name, parent_area: v.parent_area, sort_order: areas.value.length + 1 })
  loadLookups(true)
}
onMounted(load)
</script>
<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.ar { color: var(--ink); display: flex; flex-direction: column; gap: 2px; cursor: pointer; }
.ar:hover { background: var(--soft); }
</style>
