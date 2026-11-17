<template>
  <template v-if="d">
    <div class="flex flex-wrap items-center gap-2">
      <Badge :theme="d.status === 'Someday' ? 'violet' : 'green'" :label="d.status === 'Someday' ? 'On the Someday list' : 'Brought back'" />
      <span v-if="d.someday_review_on && d.status === 'Someday'" class="text-sm text-ink-gray-6">Review on {{ short(d.someday_review_on, true) }}</span>
    </div>
    <div v-if="d.body_md"><Md :text="d.body_md" /></div>
    <div v-else class="text-base text-ink-gray-6">No more detail.</div>
    <div class="text-sm text-ink-gray-6">
      <div v-if="d.source_name">From <a class="text-ink-blue-8 hover:underline" href="#" @click.prevent="openSource">{{ d.source_title || d.source_name }}</a></div>
      <div v-if="d.someday_note">Why it can wait: {{ d.someday_note }}</div>
      <div>Created {{ short(d.creation, true) }}<span v-if="d.someday_on"> · parked {{ short(d.someday_on, true) }}</span></div>
      <div v-if="d.brought_to_name">Became <a class="text-ink-blue-8 hover:underline" href="#" @click.prevent="openMade">a {{ MADE[d.brought_to_doctype] }}</a></div>
    </div>
    <div v-if="writable && d.status === 'Someday'" class="flex flex-wrap gap-2">
      <Button variant="solid" label="Bring back" data-idea-bring-back @click="askBringBack({ ...d, doctype: 'Life Idea' })" />
      <Button label="Keep for 3 more months" @click="keepIt" />
      <Button variant="ghost" theme="red" label="Purge" @click="purgeIt" />
    </div>
    <NewRecord v-if="bringBack.open" v-model="bringBack.open" :title="`Bring back ${d.title}`" action="Bring back" :fields="bringBack.fields" :initial="bringBack.initial"
      :save="doBringBack" @saved="load(); emit('changed')" />
  </template>
</template>
<script setup>
// An idea on the Someday list: its text, where it came from, and Bring back, Keep or Purge.
import { computed, onMounted, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import Md from '../Md.vue'
import NewRecord from '../NewRecord.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { openRef, refOf } from '@/lib/pane'
import { askBringBack, bringBack, doBringBack, keep, purge } from '@/lib/someday'

const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const MADE = { 'Life Task': 'task', 'Life Goal': 'goal', 'Life Note': 'note' }
const d = ref(null)
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write' && !store.isAgent)
async function load() {
  try {
    d.value = await api('someday.get_idea', { idea: props.name })
    emit('meta', { title: d.value.title, area: d.value.area, area_name: d.value.area_name, goal: d.value.goal })
  } catch (e) {
    emit('missing')
  }
}
const openSource = () => openRef(refOf(d.value.source_doctype, d.value.source_name) || (d.value.source_doctype === 'Life Inbox Item' ? 'source:' + d.value.source_name : null))
const openMade = () => openRef(refOf(d.value.brought_to_doctype, d.value.brought_to_name))
async function keepIt() { await keep({ ...d.value, doctype: 'Life Idea' }); load() }
async function purgeIt() { if (await purge({ ...d.value, doctype: 'Life Idea' })) emit('close') }
onMounted(load)
</script>
