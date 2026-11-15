<template>
  <PageHead title="Areas" :sub="`${store.space} · where records are filed`">
    <Button v-if="canWrite()" variant="solid" label="New area" @click="newOpen = true" />
  </PageHead>
  <div class="page-body">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
      <Card v-for="a in top" :key="a.name" class="relative flex cursor-pointer flex-col gap-0.5 hover:bg-surface-gray-1">
        <RouterLink class="absolute inset-0 rounded-5 focus-visible:focus-ring" :to="`/areas/${a.name}`" :aria-label="a.area_name" />
        <b class="break-words text-base font-semibold text-ink-gray-9">{{ a.area_name }}</b>
        <div class="text-sm text-ink-gray-6"><NumLink class="relative" :to="{ path: '/projects', query: { area: a.name, status: 'Active' } }">{{ a.projects }} active project{{ a.projects === 1 ? '' : 's' }}</NumLink> ·
          <NumLink class="relative" :to="{ path: '/tasks', query: { area: a.name, view: 'list' } }">{{ a.open_tasks }} open task{{ a.open_tasks === 1 ? '' : 's' }}</NumLink> ·
          <NumLink class="relative" :to="{ path: '/library', query: { view: 'list', area: a.name } }">{{ a.notes }} note{{ a.notes === 1 ? '' : 's' }}</NumLink></div>
        <div v-if="children(a).length" class="chips mt-1.5">
          <Button v-for="c in children(a)" :key="c.name" class="relative" size="sm" :label="c.area_name" :route="`/areas/${c.name}`" />
        </div>
      </Card>
    </div>
    <Card v-if="loaded && !top.length"><Empty title="No areas yet." hint="Areas are your own filing headings, such as Family or Work. Add one with New area." /></Card>
    <p v-if="unfiled" class="text-sm text-ink-gray-6"><NumLink :to="{ path: '/tasks', query: { area: 'none', view: 'list' } }">{{ unfiled }} open task{{ unfiled === 1 ? '' : 's' }}</NumLink> {{ unfiled === 1 ? 'has' : 'have' }} no area yet. Open the list to file them.</p>
  </div>
  <NewRecord v-model="newOpen" title="New area" action="Add area" :fields="FIELDS" :save="create" @saved="load" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
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
