<template>
  <div class="pj rowlink" :class="{ on: current && current.ref === 'project:' + p.name }" tabindex="0" :data-ref="'project:' + p.name" @click="open" @keydown.enter.self="open">
    <div style="display: flex; justify-content: space-between; gap: 8px; align-items: flex-start">
      <b class="ttl" style="font-weight: 600">{{ p.title }}</b>
      <span class="pl" :class="p.status === 'Active' ? 'g' : p.status === 'On Hold' ? 'n' : 'b'">{{ p.status === 'On Hold' ? 'On hold' : p.status }}</span>
    </div>
    <div v-if="p.outcome" class="mt">Outcome: {{ p.outcome.replace(/^./, (c) => c.toLowerCase()) }}</div>
    <div class="br" style="flex-grow: 0"><i :style="`width: ${p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0}%`"></i></div>
    <div class="mt"><RouterLink class="num" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</RouterLink> · {{ tail }}</div>
  </div>
</template>
<script setup>
// A project card. Clicking it opens the project summary in the pane; the full page is one step further.
import { computed } from 'vue'
import { short } from '@/lib/dates'
import { doneLink } from '@/lib/tasks'
import { current, openRef } from '@/lib/pane'

const props = defineProps({ p: Object })
const tail = computed(() => (props.p.status === 'On Hold' && props.p.waiting_on ? 'waiting on ' + props.p.waiting_on : props.p.target_date ? 'target ' + short(props.p.target_date) : 'no target date'))
function open(e) {
  if (e.target.closest && e.target.closest('a')) return
  openRef('project:' + props.p.name)
}
</script>
<style scoped>
.pj { border: 1px solid var(--outline-gray-1); border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; color: var(--ink-gray-9); }
.pj:hover { background: var(--surface-gray-1); }
.pj.on { border-color: var(--ink-blue-8); background: var(--surface-blue-2); }
</style>
