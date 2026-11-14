<template>
  <Teleport to="#jr-actions"><RouterLink class="bt p" to="/inbox" style="color: var(--bg)">Add a page photo</RouterLink></Teleport>
  <div class="bd">
    <div v-if="pages.length" class="gal">
      <RouterLink v-for="p in pages" :key="p.name" class="cd pg" :to="`/journal/pages/${p.name}`">
        <div class="thumb"><img v-if="p.image" :src="p.image" :alt="`Journal page ${p.page_number || ''}`" loading="lazy" /><span v-else class="mt">No image</span></div>
        <b style="font-weight: 500">{{ p.page_number ? `Page ${p.page_number}` : 'Page' }}</b><div class="mt">{{ long(p.page_date, true) }}</div>
      </RouterLink>
    </div>
    <div v-else-if="loaded" class="cd"><Empty title="No journal pages yet." hint="Photograph a page of the paper journal and drop it in the Inbox. Accept the Journal page proposal and it shows here with its transcript." /></div>
    <div v-if="more"><button class="bt s" type="button" @click="load(true)">Show earlier pages</button></div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import Empty from '@/components/Empty.vue'
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
.gal { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.pg { color: var(--ink); text-decoration: none; display: flex; flex-direction: column; gap: 2px; padding: 10px; }
.pg:hover { background: var(--soft); }
.thumb { aspect-ratio: 3 / 4; background: var(--soft); border-radius: 6px; overflow: hidden; display: grid; place-items: center; margin-bottom: 6px; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
</style>
