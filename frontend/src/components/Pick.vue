<template>
  <Dropdown :options="menu">
    <Button size="sm" :variant="label ? 'subtle' : 'outline'" :icon-left="label ? undefined : 'lucide-plus'" :disabled="disabled" :label="label ? prefix + label : placeholder" icon-right="lucide-chevron-down" />
  </Dropdown>
</template>
<script setup>
// A value that changes with one tap: tap the button, pick from the menu. Used for the filing of a record (area, goal).
import { computed } from 'vue'
import { Button, Dropdown } from 'frappe-ui'

const props = defineProps({
  modelValue: { type: [String, null], default: null },
  options: { type: Array, default: () => [] }, // [{ value, label, title? }]
  placeholder: String, prefix: { type: String, default: '' }, clearable: { type: Boolean, default: true }, disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const label = computed(() => { const o = props.options.find((x) => x.value === props.modelValue); return o?.title || o?.label || '' }) // title: the full name when the label is short or indented
const menu = computed(() => {
  const items = props.options.map((o) => ({ label: o.label, selected: o.value === props.modelValue, onClick: () => emit('update:modelValue', o.value) }))
  if (props.clearable && props.modelValue) items.push({ label: 'Remove', icon: 'lucide-x', onClick: () => emit('update:modelValue', null) })
  if (!items.length) items.push({ label: 'Nothing to choose from yet', disabled: true, onClick: () => {} })
  return items
})
</script>
