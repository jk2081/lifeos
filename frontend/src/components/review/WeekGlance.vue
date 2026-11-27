<template>
  <div class="flex min-w-0 flex-col" data-week-glance>
    <div class="grid border-b border-outline-gray-1" :style="cols">
      <div v-for="d in g.days" :key="d.date" class="py-1.5 text-center text-sm text-ink-gray-7">{{ d.label }}</div>
    </div>
    <div class="grid" :style="cols">
      <div v-for="d in g.days" :key="d.date" class="relative border-r border-outline-gray-1 last:border-r-0" :style="{ height: HEIGHT + 'px' }" :data-glance-day="d.date">
        <template v-for="b in d.blocks" :key="b.start + b.title">
          <Button v-if="b.kind === 'goal' && b.goal" variant="subtle" size="sm" class="!absolute inset-x-1 !h-auto !min-h-0 !items-start !justify-start overflow-hidden !rounded-1 border border-outline-blue-6 !bg-surface-blue-2 !px-1 !py-0.5 !text-xs !text-ink-blue-8"
            :style="place(b)" :label="b.title" :data-glance-goal="b.goal" @click="emit('open', b.goal)"><span class="truncate">{{ b.title }}</span></Button>
          <button v-else-if="b.ref" type="button" class="absolute inset-x-1 cursor-pointer overflow-hidden rounded-1 bg-surface-gray-2 px-1 py-0.5 text-left text-xs text-ink-gray-7 hover:bg-surface-gray-3 focus-visible:focus-ring"
            :style="place(b)" :title="b.title" :data-ref="b.ref" data-glance-event @click="emit('ref', b.ref)"><span class="block truncate">{{ b.title }}</span></button>
          <div v-else class="absolute inset-x-1 overflow-hidden rounded-1 bg-surface-gray-2 px-1 py-0.5 text-xs text-ink-gray-7" :style="place(b)" :title="b.title" data-glance-event>
            <span class="block truncate">{{ b.title }}</span></div>
        </template>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-3 border-t border-outline-gray-1 px-2 py-1.5 text-xs text-ink-gray-7">
      <span class="flex items-center gap-1"><span class="size-2.5 rounded-1 border border-outline-blue-6 bg-surface-blue-2" aria-hidden="true" />goal work</span>
      <span class="flex items-center gap-1"><span class="size-2.5 rounded-1 bg-surface-gray-2" aria-hidden="true" />existing</span>
      <span>· click a block to edit it</span>
    </div>
  </div>
</template>
<script setup>
// Next week at a glance (board 31): working days, existing events in grey, goal work in blue, placed by time inside the
// working day. Clicking a goal block opens that goal's drawer. A glance, not an editor: dragging is on Plan > Week.
import { computed } from 'vue'
import { Button } from 'frappe-ui'

const HEIGHT = 260
const props = defineProps({ g: Object })
const emit = defineEmits(['open'])
const cols = computed(() => ({ gridTemplateColumns: `repeat(${props.g.days.length || 1}, minmax(0, 1fr))` }))
const mins = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m }
const span = computed(() => Math.max(mins(props.g.end) - mins(props.g.start), 60))
function place(b) {
  const at = mins(b.start.slice(11, 16)) - mins(props.g.start)
  const top = Math.max(0, Math.min(HEIGHT - 14, (HEIGHT * at) / span.value))
  const height = Math.max(14, Math.min(HEIGHT - top, (HEIGHT * b.minutes) / span.value))
  return { top: top + 'px', height: height + 'px' }
}
</script>
