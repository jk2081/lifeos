<template>
  <OptionPicker :model-value="modelValue" :items="items" v-model:query="query" :shown="shown" :label="label" :placeholder="placeholder" :disabled="disabled" :clearable="clearable" prefix="goal"
    search-placeholder="Search goals" empty-text="No goal found" @update:model-value="(v) => emit('update:modelValue', v)" />
</template>
<script setup>
// The searchable goal picker: goals in progress, each with its horizon (12 weeks, Month, Year, Long term), a search that matches any word of the title.
// `options` replaces the list when the goal can only be one of some (what a goal serves). A thin wrapper on OptionPicker.
import { computed, ref } from 'vue'
import OptionPicker from './OptionPicker.vue'
import { goalOptions, loadLookups } from '@/lib/lookups'

const props = defineProps({ modelValue: { type: String, default: '' }, label: { type: String, default: '' }, placeholder: { type: String, default: 'Choose a goal' },
  disabled: Boolean, clearable: { type: Boolean, default: true }, options: { type: Array, default: null } })
const emit = defineEmits(['update:modelValue'])
const query = ref('')
loadLookups()
const all = computed(() => (props.options || goalOptions(undefined, { empty: null })).filter((o) => o.value))
const words = computed(() => query.value.toLowerCase().split(/\s+/).filter(Boolean))
const items = computed(() => all.value.filter((o) => words.value.every((w) => o.label.toLowerCase().includes(w))))
const shown = computed(() => all.value.find((o) => o.value === props.modelValue)?.label || '')
</script>
