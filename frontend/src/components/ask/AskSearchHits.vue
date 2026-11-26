<template>
  <section v-if="rows.length" class="flex flex-col gap-1" data-ask-search-hits>
    <div class="text-sm text-ink-gray-6">Found for “{{ query }}”</div>
    <button v-for="r in rows" :key="r.ref_doctype + r.ref_name" type="button" data-ask-search-hit
      class="flex min-w-0 items-center gap-2 rounded-5 border border-outline-gray-2 px-3 py-2 text-left hover:bg-surface-gray-2 focus-visible:focus-ring" @click="open(r)">
      <span class="flex min-w-0 flex-1 flex-col">
        <span class="truncate text-base-medium text-ink-gray-9">{{ r.title || 'Untitled' }}</span>
        <span class="truncate text-sm text-ink-gray-6">{{ [r.area_name, short(r.record_date, true)].filter(Boolean).join(' · ') }}</span>
      </span>
      <Badge :label="r.kind" />
    </button>
  </section>
</template>
<script setup>
// What search finds for the words of a question, shown under "Chat needs an AI key" so that the question is not wasted (issue 98).
import { ref, watch } from 'vue'
import { Badge } from 'frappe-ui'
import { libraryData } from '@/data/library'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { ask } from '@/lib/ask'
import { openHit } from '@/lib/search'

const props = defineProps({ query: { type: String, required: true } })
const rows = ref([])
async function load() {
  rows.value = []
  if (!props.query.trim()) return
  const q = props.query
  try {
    const res = await libraryData.search.query({ text: q, limit: 8, ...(store.lensArea ? { space: store.space, area: store.lensArea } : {}) })
    if (q === props.query) rows.value = res.results
  } catch (e) {
    rows.value = []
  }
}
function open(r) {
  ask.open = false
  openHit(r)
}
watch(() => props.query, load, { immediate: true })
</script>
