<template>
  <Teleport to="#jr-actions"><Button variant="solid" label="Add a page photo" route="/inbox" /></Teleport>
  <div class="page-body">
    <div v-if="pages.length" class="gal">
      <RouterLink v-for="p in pages" :key="p.name" class="flex flex-col gap-0.5 rounded-5 border border-outline-gray-2 bg-surface-base p-2.5 text-ink-gray-9 hover:bg-surface-gray-1 focus-visible:focus-ring" :to="`/journal/pages/${p.name}`">
        <div class="mb-1.5 grid aspect-[3/4] place-items-center overflow-hidden rounded-4 bg-surface-gray-1"><img v-if="p.image" class="size-full object-cover" :src="p.image" :alt="`Journal page ${p.page_number || ''}`" loading="lazy" /><span v-else class="text-sm text-ink-gray-6">No image</span></div>
        <b class="font-medium">{{ p.page_number ? `Page ${p.page_number}` : 'Page' }}</b><div class="text-sm text-ink-gray-6">{{ long(p.page_date, true) }}</div>
      </RouterLink>
    </div>
    <Card v-else-if="loaded"><Empty title="No journal pages yet." hint="Photograph a page of the paper journal and drop it in the Inbox. Accept the Journal page proposal and it shows here with its transcript." /></Card>
    <div v-if="more"><Button label="Show earlier pages" @click="load(true)" /></div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { long } from '@/lib/dates'

const emit = defineEmits(['sub'])
const pages = ref([])
const more = ref(false)
const loaded = ref(false)
async function load(append = false) {
  const res = await tryCall(() => api('journal.pages', { space: store.space, start: append ? pages.value.length : 0 }))
  if (res) {
    pages.value = append ? [...pages.value, ...res.pages] : res.pages
    more.value = res.has_more
    loaded.value = true
  }
}
onMounted(() => {
  emit('sub', 'Photographed pages of the paper journal, by date')
  load()
})
</script>
<style scoped>
/* geometry only: as many page tiles as fit */
.gal { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
</style>
