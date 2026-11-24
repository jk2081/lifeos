<template>
  <nav v-if="pins.list.length" :class="variant === 'phone' ? 'flex flex-col gap-0.5 border-b border-outline-gray-1 px-3 py-2' : 'ml-4 flex flex-col gap-0.5 border-l border-outline-gray-2 pl-1.5'"
    aria-label="Pinned pages" :data-pinned-pages="variant">
    <div v-if="variant === 'phone'" class="px-2 pb-0.5 text-sm text-ink-gray-6">Pinned pages</div>
    <RouterLink v-for="p in pins.list" :key="p.doctype + p.name" :to="pagePath(p.doctype, p.name)" draggable="true"
      class="flex min-h-8 min-w-0 items-center gap-2 rounded px-2 text-base text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:focus-ring max-md:min-h-10"
      :class="[dragging === key(p) && 'opacity-50', current === key(p) && 'bg-surface-gray-2']" :aria-current="current === key(p) ? 'page' : undefined"
      data-pin :data-pin-name="p.name" :data-pin-kind="p.kind" :data-pin-new="p.new"
      @dragstart="onStart($event, p)" @dragover.prevent @drop.prevent="onDrop(p)" @dragend="dragging = ''">
      <span :class="KIND_ICON[p.kind]" class="size-4 flex-none text-ink-gray-6" aria-hidden="true" data-pin-icon />
      <span class="min-w-0 flex-1 truncate" data-pin-title>{{ p.title }}</span>
      <span v-if="p.new" class="flex-none text-sm tabular-nums text-ink-gray-6" data-pin-count>· {{ p.new }}</span>
    </RouterLink>
  </nav>
</template>
<script setup>
// Pinned pages (issue 111), with the kind icon and no group headings, in the owner's order, which they change by dragging. A count follows the
// title when something was linked since the page was last opened ("Ambaji Foods · 2").
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { KIND_ICON, pagePath, pins, reorder } from '@/lib/pins'

defineProps({ variant: { type: String, default: 'sidebar' } })
const route = useRoute()
const dragging = ref('')
const key = (p) => `${p.doctype}:${p.name}`
const current = computed(() => (route.params.doctype && route.params.name ? `${route.params.doctype}:${route.params.name}` : ''))
function onStart(e, p) {
  dragging.value = key(p)
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', key(p))
}
function onDrop(target) {
  const from = dragging.value
  dragging.value = ''
  if (!from || from === key(target)) return
  const order = pins.list.map(key).filter((k) => k !== from)
  order.splice(order.indexOf(key(target)) + (pins.list.findIndex((p) => key(p) === from) < pins.list.findIndex((p) => key(p) === key(target)) ? 1 : 0), 0, from)
  reorder(order)
}
</script>
