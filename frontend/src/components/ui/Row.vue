<template>
  <component :is="as" class="relative border-b border-outline-gray-1 last:border-b-0"
    :class="[bare ? '' : 'flex items-start gap-2.5 py-2.5', pane && 'cursor-pointer -mx-4 px-4 hover:bg-surface-gray-1', on && '!bg-surface-gray-3']" data-row :data-active="on || undefined">
    <button v-if="pane" type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="label || 'Open'" :data-ref="pane" @click="openRef(pane)" />
    <slot />
  </component>
</template>
<script setup>
// One row in a Card. With `pane` it opens that record in the record pane: a stretched button covers the row, as frappe-ui's
// list guide describes, so links and checkboxes inside the row (give them the class `relative`) still work on their own.
// `as` is the tag (`li` inside a `ul`, `label` for a row that is one control). `bare` keeps the border and the pane behaviour and leaves the
// layout (flex, grid, gap, padding) to the row's own classes, for a row that is a grid or a column.
import { computed } from 'vue'
import { current, openRef } from '@/lib/pane'
const props = defineProps({ pane: { type: String, default: null }, label: String, as: { type: String, default: 'div' }, bare: Boolean })
const on = computed(() => !!props.pane && current.value?.ref === props.pane)
</script>
