<template>
  <GroupByTable v-if="list.view.groupBy.value" v-model:group-by="list.view.groupBy.value" :doctype="list.doctype" :rows="rows" :totals="totals" :loading="loading">
    <template #cell="{ row, column, value }">
      <slot name="cell" :row="row" :column="column" :value="value">
        <span class="truncate text-base text-ink-gray-8">{{ column.kind === 'group' ? (row[column.key + '__label'] ?? (value || 'Not set')) : value }}</span>
      </slot>
    </template>
  </GroupByTable>
</template>
<script setup>
// The table of groups shown while a list is grouped. The rows come from our own list methods (their `summary` argument),
// which label a Link with the title of the record it points to. Wraps @framework/ui GroupByTable.
import { GroupByTable } from '@framework/ui/GroupBy'
defineProps({ list: { type: Object, required: true }, rows: { type: Array, default: () => [] }, totals: { type: Object, default: null }, loading: Boolean })
</script>
