<template>
  <template v-if="d">
    <section v-if="on('page')">
      <div v-if="d.image" class="max-h-[60vh] overflow-auto rounded-5 border border-outline-gray-1 bg-surface-gray-1" :class="zoom ? 'cursor-zoom-out' : 'cursor-zoom-in'" @click="zoom = !zoom">
        <img class="block h-auto" :class="zoom ? 'w-[220%] max-w-none' : 'w-full'" :src="d.image" alt="Photographed journal page" /></div>
      <Card v-else><Empty title="No image." hint="This page has a transcript but no photograph." /></Card></section>
    <section v-if="on('transcript')">
      <Card><Md v-if="d.transcript_md" :text="d.transcript_md" read /><Empty v-else title="No transcript." hint="Open the full page to type what the page says." /></Card></section>
    <section v-if="on('created')">
      <Card flush><Row v-for="c in d.created" :key="c.route" :pane="refOfRoute(c.route)" :label="c.title" @click="!refOfRoute(c.route) && openRoute(c.route)">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ c.title }}</div><div class="text-sm text-ink-gray-6">{{ c.kind }}</div></div></Row>
        <Empty v-if="!d.created.length" title="Nothing created from this page yet." hint="Records made when its inbox item is reviewed show here." /></Card></section>
    <div v-if="d.inbox_item && on('page')" class="text-sm text-ink-gray-6"><a class="text-ink-blue-8 hover:underline" href="#" @click.prevent="openRef('inbox:' + d.inbox_item)">Open the inbox item it came from</a></div>
  </template>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import Md from '../Md.vue'
import Empty from '../Empty.vue'
import { api } from '@/lib/api'
import { long } from '@/lib/dates'
import { areaName, loadLookups } from '@/lib/lookups'
import { openRef, openRoute, refOfRoute } from '@/lib/pane'

const props = defineProps({ name: String, type: String, tab: String })
// the pane's tabs: Page, Transcript, Created from this page
const on = (t) => !props.tab || props.tab === t
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const d = ref(null)
const zoom = ref(false)
onMounted(async () => {
  try {
    d.value = await api('journal.page_detail', { page: props.name })
    await loadLookups()
    emit('meta', { title: d.value.page_number ? `Journal page ${d.value.page_number}` : 'Journal page', sub: long(d.value.page_date, true),
      area: d.value.area, area_name: areaName(d.value.area), fullPage: null, sensitive: { doctype: 'Life Journal Page', name: d.value.name, on: !!d.value.is_sensitive },
      tabs: [{ value: 'page', label: 'Page' }, { value: 'transcript', label: 'Transcript' }, { value: 'created', label: 'Created from this page', count: d.value.created.length, noun: 'records' }] })
  } catch (e) {
    emit('missing')
  }
})
</script>
