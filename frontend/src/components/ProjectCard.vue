<template>
  <div class="relative flex cursor-pointer flex-col gap-1.5 rounded-5 border p-4 hover:bg-surface-gray-1"
    :class="on ? 'border-outline-gray-4 !bg-surface-gray-3' : 'border-outline-gray-2'" data-row :data-active="on || undefined">
    <button type="button" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="p.title" :data-ref="'project:' + p.name" @click="openRef('project:' + p.name)" />
    <div class="flex items-start justify-between gap-2">
      <b class="break-words text-base font-semibold text-ink-gray-9">{{ p.title }}</b>
      <Badge :theme="p.status === 'Active' ? 'green' : p.status === 'On Hold' ? 'gray' : 'blue'" :label="p.status === 'On Hold' ? 'On hold' : p.status" />
    </div>
    <div v-if="p.outcome" class="text-sm text-ink-gray-6">Outcome: {{ p.outcome.replace(/^./, (c) => c.toLowerCase()) }}</div>
    <Progress size="sm" :value="p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0" />
    <div class="text-sm text-ink-gray-6"><NumLink class="relative" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</NumLink> · {{ tail }}</div>
  </div>
</template>
<script setup>
// A project card. Clicking it opens the project summary in the pane; the full page is one step further.
import { computed } from 'vue'
import { Badge, Progress } from 'frappe-ui'
import NumLink from './ui/NumLink.vue'
import { short } from '@/lib/dates'
import { doneLink } from '@/lib/tasks'
import { current, openRef } from '@/lib/pane'

const props = defineProps({ p: Object })
const on = computed(() => current.value?.ref === 'project:' + props.p.name)
const tail = computed(() => (props.p.status === 'On Hold' && props.p.waiting_on ? 'waiting on ' + props.p.waiting_on : props.p.target_date ? 'target ' + short(props.p.target_date) : 'no target date'))
</script>
