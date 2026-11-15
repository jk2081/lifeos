<template>
  <div class="rw" :class="{ gone: task._done, on: current && current.ref === 'task:' + task.name }" :data-ref="'task:' + task.name" tabindex="0" @keydown.enter.self="$emit('open', task)">
    <input class="ck" type="checkbox" :checked="task.status === 'Done'" :disabled="readonly" :aria-label="'Done: ' + task.title" @change="$emit('toggle', task)" />
    <div class="grow" style="cursor: pointer" @click="$emit('open', task)">
      <div class="ttl" :style="task.status === 'Done' || task.status === 'Dropped' ? 'text-decoration: line-through; color: var(--ink-gray-6)' : ''">{{ task.title }}</div>
      <div class="mt">{{ taskMeta(task, today, { withDue }) }}</div>
    </div>
    <span v-if="pill" class="pl" :class="pill.cls"><span class="only-desktop">{{ pill.text }}</span><span class="only-phone">{{ pill.shortText || pill.text }}</span></span>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { taskMeta, taskPill } from '@/lib/tasks'
import { current } from '@/lib/pane'

const props = defineProps({ task: Object, today: String, withDue: Boolean, readonly: Boolean })
defineEmits(['toggle', 'open'])
const pill = computed(() => taskPill(props.task, props.today))
</script>
<style scoped>
.gone { opacity: 0.45; transition: opacity 0.2s; }
</style>
