<template>
  <RouterLink class="pj" :to="`/projects/${p.name}`">
    <div style="display: flex; justify-content: space-between; gap: 8px; align-items: flex-start">
      <b style="font-weight: 600">{{ p.title }}</b>
      <span class="pl" :class="p.status === 'Active' ? 'g' : p.status === 'On Hold' ? 'n' : 'b'">{{ p.status === 'On Hold' ? 'On hold' : p.status }}</span>
    </div>
    <div v-if="p.outcome" class="mt">Outcome: {{ p.outcome.replace(/^./, (c) => c.toLowerCase()) }}</div>
    <div class="br" style="flex-grow: 0"><i :style="`width: ${p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0}%`"></i></div>
    <div class="mt">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done · {{ tail }}</div>
  </RouterLink>
</template>
<script setup>
import { computed } from 'vue'
import { short } from '@/lib/dates'

const props = defineProps({ p: Object })
const tail = computed(() => (props.p.status === 'On Hold' && props.p.waiting_on ? 'waiting on ' + props.p.waiting_on : props.p.target_date ? 'target ' + short(props.p.target_date) : 'no target date'))
</script>
<style scoped>
.pj { border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; text-decoration: none; color: var(--ink); }
.pj:hover { background: var(--soft); color: var(--ink); }
</style>
