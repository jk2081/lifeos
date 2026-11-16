<template>
  <Row :pane="'task:' + task.name" :label="task.title" class="transition-opacity" :class="task._done && 'opacity-45'" data-task-row>
    <Checkbox class="relative mt-0.5" :model-value="task.status === 'Done'" :disabled="readonly" :aria-label="'Done: ' + task.title" @update:model-value="$emit('toggle', task)" />
    <div class="min-w-0 flex-1" data-row-main>
      <div class="break-words text-base-medium" :class="closed ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ task.title }}</div>
      <div class="text-sm text-ink-gray-6">{{ taskMeta(task, today, { withDue }) }}</div>
    </div>
    <Badge v-if="pill" :theme="pill.theme"><span class="max-md:hidden">{{ pill.text }}</span><span class="md:hidden">{{ pill.shortText || pill.text }}</span></Badge>
    <slot name="end" />
  </Row>
</template>
<script setup>
// A task in a section list: tick it off with the checkbox, open it in the pane by clicking anywhere else on the row.
import { computed } from 'vue'
import { Badge, Checkbox } from 'frappe-ui'
import Row from './ui/Row.vue'
import { taskMeta, taskPill } from '@/lib/tasks'

const props = defineProps({ task: Object, today: String, withDue: Boolean, readonly: Boolean })
defineEmits(['toggle'])
const pill = computed(() => taskPill(props.task, props.today))
const closed = computed(() => props.task.status === 'Done' || props.task.status === 'Dropped')
</script>
