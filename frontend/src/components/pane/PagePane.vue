<template>
  <template v-if="d">
    <section><h2 class="sh">Page</h2>
      <div v-if="d.image" class="imgwrap" :class="{ zoom }" @click="zoom = !zoom"><img :src="d.image" alt="Photographed journal page" /></div>
      <div v-else class="cd"><Empty title="No image." hint="This page has a transcript but no photograph." /></div></section>
    <section><h2 class="sh">Transcript</h2>
      <div class="cd"><Md v-if="d.transcript_md" :text="d.transcript_md" read /><Empty v-else title="No transcript." hint="Open the full page to type what the page says." /></div></section>
    <section v-if="d.created.length"><h2 class="sh">Created from this page</h2>
      <div class="cd list"><div v-for="c in d.created" :key="c.route" class="rw rowlink" @click="openRoute(c.route)"><div class="grow"><div class="ttl">{{ c.title }}</div><div class="mt">{{ c.kind }}</div></div></div></div></section>
    <div v-if="d.inbox_item" class="mt"><a href="#" @click.prevent="openRef('inbox:' + d.inbox_item)">Open the inbox item it came from</a></div>
  </template>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import { api } from '@/lib/api'
import { long } from '@/lib/dates'
import { areaName, loadLookups } from '@/lib/lookups'
import { openRef, openRoute } from '@/lib/pane'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const d = ref(null)
const zoom = ref(false)
onMounted(async () => {
  try {
    d.value = await api('journal.page_detail', { page: props.name })
    await loadLookups()
    emit('meta', { title: d.value.page_number ? `Journal page ${d.value.page_number}` : 'Journal page', sub: long(d.value.page_date, true),
      area: d.value.area, area_name: areaName(d.value.area), fullPage: `/journal/pages/${d.value.name}` })
  } catch (e) {
    emit('missing')
  }
})
</script>
<style scoped>
.imgwrap { border: 1px solid var(--line); border-radius: 10px; background: var(--soft); overflow: auto; max-height: 60vh; cursor: zoom-in; }
.imgwrap img { display: block; width: 100%; height: auto; }
.imgwrap.zoom { cursor: zoom-out; }
.imgwrap.zoom img { width: 220%; max-width: none; }
</style>
