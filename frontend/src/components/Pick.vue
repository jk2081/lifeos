<template>
  <Dropdown :options="menu">
    <button class="ch sm" :class="{ add: !label }" type="button" :disabled="disabled">
      <template v-if="label">{{ prefix }}{{ label }}</template>
      <template v-else>+ {{ placeholder }}</template>
    </button>
  </Dropdown>
</template>
<script setup>
// A chip that changes its value with one tap: tap, pick from the list.
import { computed } from 'vue'
import { Dropdown } from 'frappe-ui'

const props = defineProps({
  modelValue: { type: [String, null], default: null },
  options: { type: Array, default: () => [] }, // [{ value, label }]
  placeholder: String, prefix: { type: String, default: '' }, clearable: { type: Boolean, default: true }, disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const label = computed(() => props.options.find((o) => o.value === props.modelValue)?.label || '')
const menu = computed(() => {
  const items = props.options.map((o) => ({ label: o.label + (o.value === props.modelValue ? '  ✓' : ''), onClick: () => emit('update:modelValue', o.value) }))
  if (props.clearable && props.modelValue) items.push({ label: 'Remove', onClick: () => emit('update:modelValue', null) })
  if (!items.length) items.push({ label: 'Nothing to choose from yet', onClick: () => {} })
  return items
})
</script>
