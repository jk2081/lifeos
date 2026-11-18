<template>
  <!-- one finding: its kind, text and source, and one or two actions (board 28) -->
  <div class="flex flex-wrap items-start gap-x-3 gap-y-2 border-b border-outline-gray-1 py-3 last:border-b-0" data-finding :data-kind="f.kind" :data-finding-name="f.name">
    <Badge size="sm" theme="gray" :label="f.kind" class="mt-0.5" />
    <div class="min-w-0 flex-[1_1_240px]">
      <div class="text-base text-ink-gray-9">{{ f.title }}</div>
      <div v-if="f.source" class="text-sm text-ink-gray-6">{{ f.source }}</div>
    </div>
    <div class="flex flex-wrap gap-2">
      <Button v-for="a in f.actions" :key="a.index" :label="a.label" :data-finding-action="a.kind" @click="emit('act', a.index)" />
    </div>
  </div>
</template>
<script setup>
import { Badge, Button } from 'frappe-ui'
defineProps({ f: Object })
const emit = defineEmits(['act'])
</script>
